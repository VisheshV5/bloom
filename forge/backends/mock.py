"""Deterministic mock backend: canned Forge outputs and simulated agents.

It never calls a model or SuperGrid. The generalist is wrong most of the time on
categories it has no tools for; specialists use the benchmark's computed answers.
Every simulated Grid message is emitted to the event bus so the dashboard animates.
"""

from __future__ import annotations

import random
import time

from bloom.routing import classify, pick_agent
from bloom.specs import DEFAULT_SPECIALIST_MODEL
from forge.backends.base import TaskResult
from tasks import final_task

# Probability the generalist answers correctly, per category.
GENERALIST_ACCURACY = {"sql": 0.1, "stats": 0.3, "dates": 0.35, "units": 0.4, "extraction": 0.95, "writing": 0.9}
SPECIALIST_ACCURACY = 0.95
# Eval-only, SIMULATED: a generalist given every tool closes much of the gap but not all of it.
GENERALIST_TOOLS_ACCURACY = {"sql": 0.6, "stats": 0.75, "dates": 0.7, "units": 0.8, "extraction": 0.9, "writing": 0.9}
GENERALIST_TOOLS_CHECK_ACCURACY = {k: min(0.95, v + 0.07) for k, v in GENERALIST_TOOLS_ACCURACY.items()}
EVAL_ARM_ACCURACY = {"generalist": GENERALIST_ACCURACY, "generalist_tools": GENERALIST_TOOLS_ACCURACY,
                     "generalist_tools_check": GENERALIST_TOOLS_CHECK_ACCURACY}

CANNED_SPECS: dict[str, dict] = {
    "sql": {
        "slug": "sql-analyst", "category": "sql",
        "purpose": "Answers questions about the coffee sales database by writing and running SQL.",
        "instructions": ("You are a SQL analyst. Always inspect the question, write one SQLite SELECT, "
                         "run it with run_sql, and check the result before answering. Use calculate for "
                         "any follow-up arithmetic. Never guess numbers. End with `FINAL: <answer>`."),
        "tools": ["run_sql", "calculate"], "capabilities": ["sql", "database", "revenue"],
        "verify": ("Re-derive the number with a second, differently written query (e.g. aggregate per day or "
                   "per product, then sum) and check both results agree; check the filters match the question."),
    },
    "stats": {
        "slug": "stats-analyst", "category": "stats",
        "purpose": "Computes descriptive statistics, regressions, and significance tests exactly.",
        "instructions": ("You are a statistician. Parse every number from the question, call the matching "
                         "tool (describe, percentile, ttest_welch, linregress, correlation), and round only "
                         "at the end as requested. End with `FINAL: <answer>`."),
        "tools": ["describe", "percentile", "ttest_welch", "linregress", "correlation", "calculate"],
        "capabilities": ["statistics", "t-test", "regression"],
        "verify": ("Re-count the numbers you passed to the tool against the question, call the tool again, and "
                   "confirm the rounding the question asked for."),
    },
    "dates": {
        "slug": "date-wrangler", "category": "dates",
        "purpose": "Does calendar and business-day arithmetic without off-by-one errors.",
        "instructions": ("You are a calendar specialist. Use the date tools for every computation "
                         "(add_business_days, business_days_between, days_between, weekday). Re-read "
                         "whether the start day counts. Answer dates as YYYY-MM-DD. End with `FINAL: <answer>`."),
        "tools": ["add_days", "add_business_days", "business_days_between", "business_days_in_range",
                  "days_between", "weekday"],
        "capabilities": ["dates", "calendar", "business-days"],
        "verify": ("Check the answer the other way round (e.g. count business days between the start and your "
                   "answer) and re-read whether the start day counts."),
    },
    "units": {
        "slug": "unit-converter", "category": "units",
        "purpose": "Converts units and chains the arithmetic precisely.",
        "instructions": ("You convert units. Use convert_units for every conversion and calculate for "
                         "arithmetic; state each intermediate value. Round only at the end. "
                         "End with `FINAL: <answer>`."),
        "tools": ["convert_units", "calculate"], "capabilities": ["units", "conversion"],
        "verify": "Convert your answer back to the original units with convert_units and check it matches the input.",
    },
    "extraction": {
        "slug": "text-extractor", "category": "extraction",
        "purpose": "Extracts structured items from messy text with regular expressions.",
        "instructions": ("Write a precise regex, run regex_findall, then filter invalid matches. "
                         "Return items comma separated. End with `FINAL: <answer>`."),
        "tools": ["regex_findall"], "capabilities": ["extraction", "regex"],
        "verify": "Run a second, looser regex and make sure no valid item was missed and no invalid one kept.",
    },
    "writing": {
        "slug": "report-writer", "category": "writing",
        "purpose": "Turns other agents' findings into a short, accurate executive note.",
        "instructions": ("You write executive notes. Use only numbers given by other agents, keep exactly "
                         "three sentences, lead with the answer, end with a recommendation. "
                         "End with `FINAL: <the note>`."),
        "tools": [], "capabilities": ["report-writer", "writing", "summary"],
    },
}

GOOD_POSTPROCESS = (
    "    matches = re.findall(r\"FINAL:\\s*(.+)\", text or \"\")\n"
    "    return matches[-1].strip().strip(\"`*\").strip() if matches else None"
)
# A deliberately bad first draft so the demo shows the Reviewer -> Builder retry loop.
BAD_POSTPROCESS = (
    "    import numpy as np  # not available on SuperNodes\n"
    "    return str(np.round(float(text.split('FINAL:')[-1]), 3))"
)


SIM_TOOLS = {
    "sql": [("run_sql", "SELECT protocol, COUNT(*), SUM(readmitted_30d) FROM admissions GROUP BY protocol",
             "rows=[['new', 1080, 136], ['old', 565, 101]]")],
    "stats": [("ttest_welch", "a=[...30 values], b=[...30 values]", "t=5.420, df=56.15, p=1.30e-06")],
    "dates": [("add_business_days", "start=2026-04-01, days=-30", "2026-02-18"),
              ("business_days_in_range", "start=2026-04-01, end=2026-05-12", "30 dates")],
    "units": [("convert_units", "value=2.5, from=lb, to=kg", "1.13398"), ("calculate", "18.00 / 1.13398", "15.873")],
    "writing": [],
}


def simulated_trace(category: str | None, rng, checked: bool = True) -> tuple[list[dict], dict]:
    """Plausible spans for the mock demo's Trace view. Always flagged simulated by the caller."""
    t, spans, tin, tout = 0, [], 0, 0
    for name, args, result in SIM_TOOLS.get(category or "", []):
        d = int(rng.uniform(900, 2600))
        ti, to = int(rng.uniform(900, 2400)), int(rng.uniform(40, 160))
        spans.append({"kind": "model", "name": "openai/gpt-5.6-sol", "phase": "solve", "start": t, "end": t + d,
                      "tokens_in": ti, "tokens_out": to, "requested_tools": [name]})
        t += d
        spans.append({"kind": "tool", "name": name, "phase": "solve", "start": t, "end": t + int(rng.uniform(2, 40)),
                      "args": args, "result": result, "error": False})
        t = spans[-1]["end"]
        tin, tout = tin + ti, tout + to
    for phase in (["solve", "self-check"] if checked else ["solve"]):
        d = int(rng.uniform(1200, 3000))
        ti, to = int(rng.uniform(1500, 3200)), int(rng.uniform(120, 420))
        spans.append({"kind": "model", "name": "openai/gpt-5.6-sol", "phase": phase, "start": t, "end": t + d,
                      "tokens_in": ti, "tokens_out": to, "requested_tools": []})
        t += d
        tin, tout = tin + ti, tout + to
    usage = {"tokens_in": tin, "tokens_out": tout, "model_calls": sum(s["kind"] == "model" for s in spans),
             "tool_calls": sum(s["kind"] == "tool" for s in spans), "ms": t}
    return spans, usage


class MockBackend:
    name = "mock"
    has_data = True  # simulated

    def __init__(self, bus, speed: float = 1.0, seed: int = 1, flaky: tuple[str, ...] = ("stats",)):
        self.bus = bus
        self.speed = speed
        self.seed = seed
        self.flaky = set(flaky)
        self._built_once: set[str] = set()
        self._attempts: dict[str, int] = {}

    # ── helpers ────────────────────────────────────────────────────────────
    def _sleep(self, seconds: float) -> None:
        if self.speed > 0:
            time.sleep(seconds / self.speed)

    def _rng(self, *key) -> random.Random:
        return random.Random(":".join(str(k) for k in (self.seed, *key)))

    @staticmethod
    def _wrong(task: dict, rng: random.Random):
        ans, kind = task["answer"], task.get("check")
        if kind == "number":
            return round(float(ans) * (1 + rng.choice([-1, 1]) * rng.uniform(0.04, 0.2)) + rng.choice([1, -1]), 3)
        if kind == "date":
            from bloom.tools.dates import add_days
            return add_days(ans, rng.choice([-2, -1, 1, 3]))
        if kind == "set":
            items = [x.strip() for x in str(ans).split(",")]
            return ", ".join(items[:-1] or ["none"])
        return rng.choice(["I don't have access to that", "Unknown", "Monday", "Downtown", "tea"])

    def _node_label(self, entry: dict) -> tuple[str, str | None]:
        node_id = entry.get("node_id") or (entry.get("node") or {}).get("node_id")
        if entry.get("slug") == "generalist":
            return "inprocess", None
        if node_id:
            return "nodes", str(node_id)
        return "payload", None

    # ── Forge roles ────────────────────────────────────────────────────────
    def architect(self, gap: dict, registry: list[dict]) -> dict:
        self._sleep(1.2)
        category = gap.get("category") or "writing"
        base = CANNED_SPECS.get(category) or {
            "slug": f"{category}-specialist", "category": category,
            "purpose": f"Handles {category} tasks.", "tools": ["calculate"], "capabilities": [category],
            "instructions": f"You are a {category} specialist. End with `FINAL: <answer>`.",
        }
        return {**base, "model": DEFAULT_SPECIALIST_MODEL,
                "output_format": "Reasoning, then a final line `FINAL: <answer>`.", "version": 1}

    def builder(self, spec: dict, notes: list[str] | None, examples: list | None = None) -> dict:
        self._sleep(1.0)
        first = spec["slug"] not in self._built_once
        self._built_once.add(spec["slug"])
        bad = first and spec["category"] in self.flaky and not notes
        return {
            "instructions": spec["instructions"],
            "examples": [],
            "postprocess_body": BAD_POSTPROCESS if bad else GOOD_POSTPROCESS,
        }

    def reviewer_notes(self, spec: dict, source: str, results: dict) -> list[str]:
        notes = []
        for problem in results.get("static", []):
            notes.append(f"Static check failed: {problem}. Use only the stdlib `re` module.")
        tests = results.get("tests") or {}
        if tests and tests.get("passed", 0) < tests.get("required", 0):
            notes.append(f"Only {tests['passed']}/{tests['total']} test tasks passed; "
                         "tighten the instructions and always use the tools.")
        if results.get("build") and not results["build"].get("ok", True):
            notes.append("flwr build failed; see the build log.")
        return notes

    # ── task execution ─────────────────────────────────────────────────────
    def _simulate_agent(self, slug: str, task: dict, correct_p: float, node_id: str | None) -> tuple[str | None, bool]:
        n = self._attempts[f"{slug}:{task['id']}"] = self._attempts.get(f"{slug}:{task['id']}", 0) + 1
        rng = self._rng(slug, task["id"], n)
        dst = slug if slug != "generalist" else "generalist"
        self.bus.emit("message", src="bloom", dst=dst, node_id=node_id, text=task["prompt"][:140])
        self._sleep(0.5 + rng.random() * 0.5)
        ok = rng.random() < correct_p
        answer = task["answer"] if ok else self._wrong(task, rng)
        self.bus.emit("message", src=dst, dst="bloom", node_id=node_id, text=f"FINAL: {answer}")
        return str(answer), ok

    def run_task(self, task: dict, registry: list[dict], mode: str = "single") -> TaskResult:
        if task.get("id") == final_task.TASK["id"]:
            return self._run_final(registry)
        category = classify(task["prompt"])
        agent = pick_agent(category, registry)
        if agent["slug"] == "generalist":
            p = GENERALIST_ACCURACY.get(task.get("category") or category or "", 0.5)
        else:
            p = SPECIALIST_ACCURACY
        tier, node_id = self._node_label(agent)
        answer, _ = self._simulate_agent(agent["slug"], task, p, node_id)
        return TaskResult(answer=answer, output=f"FINAL: {answer}", agent=agent["slug"],
                          steps=[{"step_id": "s1", "specialist": agent["slug"], "tier": tier,
                                  "node_id": node_id, "ok": True}])

    def run_with_spec(self, spec: dict, task: dict) -> TaskResult:
        self._sleep(0.3)
        rng = self._rng("review", spec["slug"], task["id"])
        ok = rng.random() < SPECIALIST_ACCURACY
        answer = task["answer"] if ok else self._wrong(task, rng)
        return TaskResult(answer=str(answer), output=f"FINAL: {answer}", agent=spec["slug"])

    def eval_batch(self, jobs: list[dict]) -> list[dict]:
        """SIMULATED eval: per-arm accuracy profiles; only checks the plumbing, not real quality."""
        from tasks import load_benchmark

        answers = {t["id"]: t for t in load_benchmark()}
        out = []
        for j in jobs:
            task = answers[j["task_id"]]
            profile = EVAL_ARM_ACCURACY.get(j["arm"])  # "specialist"/"candidate" -> SPECIALIST_ACCURACY
            p = profile.get(task["category"], 0.5) if profile else SPECIALIST_ACCURACY
            if task.get("difficulty") == "hard":  # SIMULATED: hard tasks hurt the unfocused arms more
                p *= 0.9 if j["arm"] in ("specialist", "candidate") else 0.7
            rng = self._rng("eval", j["arm"], j["task_id"], j.get("rep", 0))
            ok = rng.random() < p
            n_tools = len(j["spec"].get("tools") or [])
            checks = bool(j["spec"].get("verify")) and n_tools > 0
            usage = {"tokens_in": int(900 + 160 * n_tools + rng.uniform(0, 600)) * (2 if checks else 1),
                     "tokens_out": int(rng.uniform(150, 450)) * (2 if checks else 1),
                     "ms": int(rng.uniform(4000, 9000) * (1.8 if checks else 1) * (1.3 if n_tools > 8 else 1)),
                     "tool_calls": (rng.randint(1, 3) if n_tools else 0) + (1 if checks else 0),
                     "model_calls": (2 if n_tools else 1) + (2 if checks else 0)}
            out.append({"arm": j["arm"], "task_id": j["task_id"], "rep": j.get("rep", 0), "ok": True,
                        "answer": str(task["answer"] if ok else self._wrong(task, rng)), "error": None,
                        "usage": usage, "checked": checks, "changed": checks and rng.random() < 0.12})
        self._sleep(1.0)
        return out

    def _run_final(self, registry: list[dict]) -> TaskResult:
        by_slug = {a["slug"]: a for a in registry}
        self.bus.emit("message", src="user", dst="bloom", node_id=None, text=final_task.PROMPT[:160])
        self._sleep(1.0)
        if not any(a.get("category") == "writing" for a in registry):
            return TaskResult(answer=None, ok=False, agent="bloom",
                              missing_capabilities=[final_task.MISSING_CAPABILITY],
                              error="planner: missing capability report-writer")
        ref = final_task.reference()
        a_, b_ = ref["per_hospital"]["Hospital A"], ref["per_hospital"]["Hospital B"]
        outputs = {
            "s1": f"Hospital A: old protocol {a_['old_readmits']}/{a_['old_n']} readmitted; new {a_['new_readmits']}/{a_['new_n']}.",
            "s2": f"Hospital B: old protocol {b_['old_readmits']}/{b_['old_n']} readmitted; new {b_['new_readmits']}/{b_['new_n']}.",
            "s3": f"Pooled readmission rate {ref['rate_old']}% -> {ref['rate_new']}% ({ref['change_pts']} pts); "
                  f"z={ref['z']}, p={ref['p_value']:.2e}, significant={ref['significant']}",
            "s4": final_task.committee_note(ref),
        }
        steps = []
        for step in final_task.PLAN:
            base = step["specialist"].split("@")[0]
            slug = step["specialist"] if base in by_slug or step["specialist"] in by_slug else "generalist"
            tier, node_id = self._node_label(by_slug.get(slug.split("@")[0], {"slug": slug}))
            for dep in step["depends_on"]:
                dep_slug = next(s["specialist"] for s in final_task.PLAN if s["step_id"] == dep)
                self.bus.emit("message", src=dep_slug, dst=slug, node_id=node_id, via="bloom",
                              text=f"handoff: {outputs[dep][:100]}")
            self.bus.emit("message", src="bloom", dst=slug, node_id=node_id, text=step["instruction"][:140])
            self._sleep(1.2)
            self.bus.emit("message", src=slug, dst="bloom", node_id=node_id, text=outputs[step["step_id"]][:160])
            steps.append({"step_id": step["step_id"], "specialist": slug, "tier": tier, "node_id": node_id, "ok": True})
        note = outputs["s4"]
        rng = self._rng("final-trace")
        clock, traced = 0, []
        for st in steps:
            cat = by_slug.get(st["specialist"].split("@")[0], {}).get("category")
            spans, usage = simulated_trace(cat, rng, checked=cat != "writing")
            start = clock + int(rng.uniform(80, 200))
            end = start + usage["ms"] + int(rng.uniform(300, 900))  # Grid hop + node startup
            traced.append({**st, "start_ms": start, "end_ms": end, "ms": end - start, "trace": spans, "usage": usage,
                           "model": "openai/gpt-5.6-sol", "checked": cat != "writing", "changed": False,
                           "message_id": f"sim-{rng.getrandbits(40):010x}",
                           "answer": outputs[st["step_id"]][:120], "instruction": next(
                               p["instruction"] for p in final_task.PLAN if p["step_id"] == st["step_id"])})
            clock = end
        self.bus.emit("trace", job_id="final-a", run_id=None, simulated=True, total_ms=clock,
                      plan_ms=int(rng.uniform(8000, 15000)), federation="(mock)", steps=traced)
        return TaskResult(answer=note, output=note, agent="writing-editor", steps=steps)
