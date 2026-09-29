"""Held-out, three-arm evaluation: is a Forge-built specialist actually better?

Arms (same model for all, same held-out TEST tasks, which the Forge never saw):
  generalist              generalist instructions, no tools              (plain "AI wrapper")
  generalist_tools        generalist instructions + EVERY Bloom tool     (the fair baseline)
  specialist              the Forge-built specialist module: instructions, curated tools,
                          worked examples (from failed DEV tasks), and its self-check step
  generalist_tools_check  optional ablation: generalist_tools + a generic self-check, to show
                          how much of any gain is "checking" vs "specialization"

Reports accuracy with Wilson 95% CIs per category and overall, and a paired comparison
(per task x repeat) of specialist vs each baseline with an exact McNemar/sign test.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from bloom.specialists import generalist
from bloom.tools import TOOL_REGISTRY
from evaluator.scorer import check
from forge.paths import RUNS

EVAL_DIR = RUNS / "eval"
ARMS = ["generalist", "generalist_tools", "specialist"]
ALL_ARMS = ARMS + ["generalist_tools_check"]
GENERIC_VERIFY = "Re-derive the answer a second way with your tools and make sure both agree."
TOOLS_ADDENDUM = (" You have tools available (SQL over the company database, statistics, dates, unit "
                  "conversion, regex, calculator); use them whenever they help you get an exact answer.")


# ── statistics ─────────────────────────────────────────────────────────────
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def bootstrap_delta_ci(rows: list[dict], a: str, b: str, n_boot: int = 4000, seed: int = 0) -> list[float] | None:
    """95% CI for accuracy(a) - accuracy(b), resampling TASKS (repeats averaged within a task)."""
    import random

    per_task: dict[str, dict[str, list[int]]] = {}
    for r in rows:
        per_task.setdefault(r["task_id"], {}).setdefault(r["arm"], []).append(int(r["correct"]))
    diffs = [sum(v[a]) / len(v[a]) - sum(v[b]) / len(v[b]) for v in per_task.values() if a in v and b in v]
    if len(diffs) < 2:
        return None
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n_boot))
    return [boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]]


def sign_test_p(wins: int, losses: int) -> float:
    """Exact two-sided binomial test on discordant pairs (McNemar exact)."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


# ── arm specs ──────────────────────────────────────────────────────────────
def specialist_spec(entry: dict, model: str) -> dict:
    """The deployed specialist as it really runs: the generated module if present, else the registry spec."""
    from bloom.specialists import load_specialist, spec_from_module

    mod = load_specialist(entry["slug"])
    spec = spec_from_module(mod) if mod else {
        "slug": entry["slug"], "tools": list(entry["spec"]["tools"]), "instructions": entry["spec"]["instructions"],
        "verify": entry["spec"].get("verify", ""), "examples": []}
    return {**spec, "model": model}  # same model as every other arm


def arm_specs(registry, category: str, model: str) -> dict[str, dict | None]:
    base = {"model": model, "instructions": generalist.INSTRUCTIONS}
    with_tools = {**base, "slug": "generalist-tools", "tools": list(TOOL_REGISTRY),
                  "instructions": generalist.INSTRUCTIONS.replace(
                      "You have no tools and no database access. ", "") + TOOLS_ADDENDUM}
    spec_entry = registry.specialist_for(category)
    return {
        "generalist": {**base, "slug": "generalist", "tools": []},
        "generalist_tools": with_tools,
        "generalist_tools_check": {**with_tools, "slug": "generalist-tools-check", "verify": GENERIC_VERIFY},
        "specialist": specialist_spec(spec_entry, model) if spec_entry else None,
    }


# ── run ────────────────────────────────────────────────────────────────────
def run_eval(backend, registry, tasks: list[dict], repeats: int = 1, model: str | None = None,
             bus=None, arms: list[str] = ARMS) -> dict:
    model = model or getattr(backend, "model", None) or generalist.MODEL  # the model that actually answers
    test = [t for t in tasks if t.get("split") == "test"]
    categories = sorted({t["category"] for t in test})
    specs = {c: arm_specs(registry, c, model) for c in categories}
    jobs = []
    for t in test:
        for arm in arms:
            spec = specs[t["category"]][arm]
            if spec is None:
                continue
            for rep in range(repeats):
                jobs.append({"arm": arm, "spec": spec, "task_id": t["id"], "prompt": t["prompt"],
                             "rep": rep, "category": t["category"]})
    if bus:
        bus.emit("phase", name=f"eval: {len(jobs)} runs on {len(test)} held-out tasks")
    started = time.monotonic()
    results = backend.eval_batch(jobs)
    by_task = {t["id"]: t for t in test}
    graded, infra = [], []
    for r in results:
        # Exclude answers that never happened (run killed, provider error, time budget): an
        # infrastructure failure is not the agent being wrong, and would bias every arm.
        if r.get("infra_error") or (not r.get("ok", True) and r.get("error")):
            infra.append(r)
            continue
        t = by_task[r["task_id"]]
        graded.append({**r, "category": t["category"], "difficulty": t.get("difficulty", "standard"),
                       "correct": bool(r.get("ok", True)) and check(t, r.get("answer"))})
    report = summarize(graded, categories, arms)
    report["arms"] = arms
    report.update({
        "infra_errors": len(infra),
        "backend": backend.name, "simulated": backend.name == "mock", "model": model, "repeats": repeats,
        "n_tasks": len(test), "n_runs": len(jobs), "seconds": round(time.monotonic() - started, 1),
        "specialists": {c: (specs[c]["specialist"] or {}).get("slug") for c in categories},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": graded,
    })
    save(report)
    if bus:
        bus.emit("eval_result", headline=report["headline"], simulated=report["simulated"])
    return report


def _acc(rows: list[dict]) -> dict:
    k, n = sum(r["correct"] for r in rows), len(rows)
    lo, hi = wilson(k, n)
    return {"correct": k, "n": n, "acc": (k / n) if n else None, "ci": [lo, hi]}


def _paired(rows: list[dict], a: str, b: str) -> dict:
    by_key: dict[tuple, dict[str, bool]] = {}
    for r in rows:
        by_key.setdefault((r["task_id"], r.get("rep", 0)), {})[r["arm"]] = r["correct"]
    pairs = [(v[a], v[b]) for v in by_key.values() if a in v and b in v]
    wins = sum(1 for x, y in pairs if x and not y)
    losses = sum(1 for x, y in pairs if y and not x)
    n = len(pairs)
    delta = (sum(x for x, _ in pairs) - sum(y for _, y in pairs)) / n if n else None
    return {"pairs": n, "wins": wins, "losses": losses, "ties": n - wins - losses,
            "delta": delta, "p": sign_test_p(wins, losses), "delta_ci": bootstrap_delta_ci(rows, a, b)}


def _cost(rows: list[dict]) -> dict:
    """Mean tokens / latency / tool calls per answer, and how often a self-check changed the answer."""
    used = [r for r in rows if r.get("usage")]
    if not used:
        return {}
    mean = lambda k: sum(float(r["usage"].get(k, 0) or 0) for r in used) / len(used)  # noqa: E731
    checked = [r for r in used if r.get("checked")]
    return {"tokens": mean("tokens_in") + mean("tokens_out"), "tokens_out": mean("tokens_out"),
            "seconds": mean("ms") / 1000, "tool_calls": mean("tool_calls"), "model_calls": mean("model_calls"),
            "self_check_rate": len(checked) / len(used),
            "self_check_changed": (sum(1 for r in checked if r.get("changed")) / len(checked)) if checked else None}


def summarize(graded: list[dict], categories: list[str], arms: list[str] = ARMS) -> dict:
    per_cat = {}
    for c in categories:
        rows = [r for r in graded if r["category"] == c]
        per_cat[c] = {arm: _acc([r for r in rows if r["arm"] == arm]) for arm in arms}
        if any(r["arm"] == "specialist" for r in rows):
            per_cat[c]["paired"] = {
                "vs_generalist": _paired(rows, "specialist", "generalist"),
                "vs_generalist_tools": _paired(rows, "specialist", "generalist_tools"),
            }
            if "generalist_tools_check" in arms:
                per_cat[c]["paired"]["vs_generalist_tools_check"] = _paired(rows, "specialist", "generalist_tools_check")
    covered = [c for c in categories if "paired" in per_cat[c]]
    rows_cov = [r for r in graded if r["category"] in covered]
    overall = {arm: _acc([r for r in rows_cov if r["arm"] == arm]) for arm in arms}
    difficulty = {}
    for d in sorted({r.get("difficulty", "standard") for r in rows_cov}):
        rows_d = [r for r in rows_cov if r.get("difficulty", "standard") == d]
        difficulty[d] = {arm: _acc([r for r in rows_d if r["arm"] == arm]) for arm in arms}
        difficulty[d]["paired"] = {"vs_generalist_tools": _paired(rows_d, "specialist", "generalist_tools")}
    cost = {arm: _cost([r for r in rows_cov if r["arm"] == arm]) for arm in arms}
    paired = {"vs_generalist": _paired(rows_cov, "specialist", "generalist"),
              "vs_generalist_tools": _paired(rows_cov, "specialist", "generalist_tools")}
    if "generalist_tools_check" in arms:
        paired["vs_generalist_tools_check"] = _paired(rows_cov, "specialist", "generalist_tools_check")
    pt = paired["vs_generalist_tools"]
    pc = lambda a: "n/a" if not overall.get(a) or overall[a]["acc"] is None else f"{100 * overall[a]['acc']:.0f}%"  # noqa: E731
    if pt["pairs"]:
        headline = (f"Specialists vs generalist+tools on {len(covered)} categories: "
                    f"{pc('specialist')} vs {pc('generalist_tools')} "
                    f"({100 * pt['delta']:+.0f} pts"
                    + (f", 95% CI {100 * pt['delta_ci'][0]:+.0f} to {100 * pt['delta_ci'][1]:+.0f}" if pt.get("delta_ci") else "")
                    + f"; {pt['wins']} wins / {pt['losses']} losses; p={pt['p']:.3g}). "
                    f"Plain generalist: {pc('generalist')}.")
    else:
        headline = "No specialists yet: nothing to compare."
    return {"categories": per_cat, "covered": covered, "overall": overall, "paired": paired, "headline": headline,
            "difficulty": difficulty, "cost": cost}


def save(report: dict) -> Path:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EVAL_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    text = json.dumps(report, indent=2, default=str)
    path.write_text(text)
    (EVAL_DIR / "latest.json").write_text(text)
    return path


LABELS = {"generalist": "generalist", "generalist_tools": "generalist+tools",
          "generalist_tools_check": "gen+tools+check", "specialist": "specialist"}


def format_table(report: dict) -> str:
    arms = report.get("arms") or ARMS
    def cell(x):
        if not x or x["n"] == 0:
            return "       n/a        "
        return f"{100 * x['acc']:4.0f}% [{100 * x['ci'][0]:3.0f}-{100 * x['ci'][1]:3.0f}] n={x['n']:<3}"

    lines = [f"Held-out eval ({'SIMULATED, mock backend' if report['simulated'] else report['backend']}; "
             f"model {report['model']}; {report['n_tasks']} test tasks x {report['repeats']} repeat(s))",
             f"{'category':12} " + " ".join(f"{LABELS[a]:>22}" for a in arms) + "   spec vs gen+tools"]
    for c, row in report["categories"].items():
        p = (row.get("paired") or {}).get("vs_generalist_tools")
        pv = f"{100 * p['delta']:+.0f} pts, {p['wins']}W/{p['losses']}L, p={p['p']:.2g}" if p else "-"
        lines.append(f"{c:12} " + " ".join(f"{cell(row.get(a)):>22}" for a in arms) + f"   {pv}")
    o = report["overall"]
    lines.append(f"{'overall*':12} " + " ".join(f"{cell(o.get(a)):>22}" for a in arms))
    lines.append("* overall = categories that have a specialist. " + report["headline"])
    return "\n".join(lines)
