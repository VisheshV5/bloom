"""SuperLink-side orchestrator: plan, route steps over the Grid, collect, answer."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field

from bloom import llm
from bloom.grid_client import GridClient
from bloom.protocol import Capabilities, Result, Step, describe_payload, proposal_payload
from bloom.routing import classify, pick_agent
from bloom.specialist import resolve_spec, run_spec

TIME_BUDGET_S = 240  # hard stop well before the 5-minute task limit
DISCOVERY_TIMEOUT_S = 20
MAX_PLAN_STEPS = 4
TIERS = ("nodes", "payload", "inprocess")

PLANNER_INSTRUCTIONS = """You are the planner of Bloom, a team of specialist agents.
Break the user's task into 1-4 steps. Assign each step to exactly one available specialist
(use "generalist" if none fits). A step may depend on earlier steps; their outputs are
passed along automatically. Specialists named <name>@<site> run AT that site with that site's
private data; when a question needs several sites, plan one step per site and a later step that
combines their (aggregate) results. If the task needs a capability no specialist has (for example
writing a polished summary when there is no writer), still plan it with "generalist" AND
list it under missing_capabilities.
Reply with JSON only:
{"steps":[{"step_id":"s1","specialist":"<slug>","instruction":"...","depends_on":[]}],
 "missing_capabilities":[{"capability":"<short-kebab-name>","category":"<category>","why":"..."}]}"""


@dataclass
class StepRecord:
    step_id: str
    specialist: str
    tier: str = ""
    node_id: str | None = None
    ok: bool = False
    ms: int = 0
    answer: str | None = None
    error: str | None = None
    instruction: str = ""
    output_preview: str = ""
    start_ms: int = 0          # relative to the start of this orchestration
    end_ms: int = 0
    message_id: str | None = None  # Grid message id (remote tiers)
    model: str = ""
    checked: bool = False
    changed: bool = False
    usage: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)  # the specialist's own spans (its clock, from 0)
    fallback: str | None = None    # why a remote attempt was retried in-process


@dataclass
class Orchestration:
    job_id: str
    records: list[StepRecord] = field(default_factory=list)
    outputs: dict[str, Result] = field(default_factory=dict)
    t0: float = field(default_factory=time.monotonic)

    def ms(self, t: float) -> int:
        return int((t - self.t0) * 1000)

    def record(self, s: Step, tier: str, node_id, res: Result | None, started: float,
               message_id=None, fallback=None, error=None) -> None:
        now = time.monotonic()
        self.records.append(StepRecord(
            s.step_id, s.specialist, tier, node_id, bool(res and res.ok), int((now - started) * 1000),
            res.answer if res else None, error or (res.error if res else None),
            start_ms=self.ms(started), end_ms=self.ms(now), message_id=message_id,
            model=res.model if res else "", checked=bool(res and res.checked), changed=bool(res and res.changed),
            usage=res.usage if res else {}, trace=res.trace if res else [], fallback=fallback))


def load_registry(context) -> list[dict]:
    raw = str(context.run_config.get("bloom.registry", "") or "")
    if raw.strip():
        try:
            reg = json.loads(raw)
            if isinstance(reg, list) and reg:
                return reg
        except ValueError:
            print("[bloom] bloom.registry is not valid JSON; using built-in generalist only")
    return [{"slug": "generalist", "kind": "generalist", "category": None,
             "purpose": "Answers anything; no tools.", "capabilities": []}]


def parse_job(text: str) -> dict:
    try:
        job = json.loads(text)
        if isinstance(job, dict) and "task" in job:
            return job
    except (TypeError, ValueError):
        pass
    return {"task": text, "mode": "plan"}


def steps_from_plan(job_id: str, raw_steps: list[dict], registry: list[dict]) -> list[Step]:
    known = {a["slug"] for a in registry}
    steps = []
    for i, s in enumerate(raw_steps[:MAX_PLAN_STEPS], 1):
        slug = s.get("specialist") if s.get("specialist") in known else "generalist"
        steps.append(Step(job_id, str(s.get("step_id") or f"s{i}"), slug, str(s.get("instruction", "")),
                          depends_on=[str(d) for d in s.get("depends_on", [])]))
    return steps


def plan(job: dict, registry: list[dict], client, model: str) -> tuple[list[Step], list[dict]]:
    job_id = job["job_id"]
    if job.get("plan"):  # planned earlier in its own run (keeps each run under the 5-minute limit)
        return steps_from_plan(job_id, job["plan"], registry), list(job.get("missing_capabilities", []))
    if job.get("mode", "single") == "single":
        agent = pick_agent(classify(job["task"]), registry)
        return [Step(job_id, "s1", agent["slug"], job["task"])], []
    roster = [{"slug": a["slug"], "category": a.get("category"), "purpose": a.get("purpose", ""),
               **({"has_database": True} if a.get("has_db") else {}),
               **({"site": a["site"]} if a.get("site") else {})} for a in registry]
    try:
        text = llm.complete(client, model=model, instructions=PLANNER_INSTRUCTIONS,
                            input=f"Available specialists: {json.dumps(roster)}\n\nTask: {job['task']}")
        data = llm.extract_json(text)
        steps = steps_from_plan(job_id, data.get("steps", []), registry)
        if steps:
            return steps, list(data.get("missing_capabilities", []))
    except Exception as exc:  # noqa: BLE001
        print(f"[bloom] planner failed ({exc}); falling back to single-step routing")
    agent = pick_agent(classify(job["task"]), registry)
    return [Step(job_id, "s1", agent["slug"], job["task"])], []


def _choose_tier(entry: dict, nodes: list[dict], forced: str, rr: list[int]) -> tuple[str, str | None]:
    if entry.get("slug") == "generalist" or not nodes or forced == "inprocess":
        return "inprocess", None
    if forced in ("auto", "nodes"):
        for n in nodes:  # Tier 1: a node dedicated to this specialist
            name = str(n.get("name") or "").split("@")[0]  # convention: <slug>@<owner>
            if name == entry["slug"] or (entry.get("node_id") and n.get("id") == str(entry["node_id"])):
                return "nodes", n["id"]
        if forced == "nodes":
            return "inprocess", None
    rr[0] += 1  # Tier 2: any node, spec in payload
    return "payload", nodes[rr[0] % len(nodes)]["id"]


def discover(grid: GridClient, nodes: list[dict], timeout: float = DISCOVERY_TIMEOUT_S) -> list[dict]:
    """Ask every node what it offers (describe -> capabilities). Silent nodes are ignored."""
    if not nodes:
        return []
    try:
        pushed = grid.push([(n["id"], describe_payload()) for n in nodes])
    except Exception as exc:  # noqa: BLE001
        print(f"[bloom] discovery push failed: {exc}")
        return []
    by_msg = {r["message_id"]: n for r, n in zip(pushed, nodes) if r.get("message_id")}
    try:
        replies, _ = grid.pull(list(by_msg), timeout) if by_msg else ([], [])
    except Exception as exc:  # noqa: BLE001
        print(f"[bloom] discovery pull failed: {exc}")
        return []
    found = []
    for m in replies:
        node = by_msg.get(m.get("reply_to_message_id"))
        if node is None or not m.get("payload"):
            continue
        try:
            caps = Capabilities.from_payload(m["payload"])
        except (ValueError, TypeError):
            continue
        found.append({**caps.__dict__, "node_id": node["id"], "node_name": caps.node_name or node.get("name")})
    return found


AWAIT_BUDGET_S = 230  # stay well inside the 5-minute task limit
AWAIT_POLL_S = 8


def ready_sites(discovered: list[dict], specialist: str) -> set[str]:
    """Sites whose node runs `specialist`, holds its database, and whose owner approved the spec."""
    return {str(d["site"]).strip().lower().replace(" ", "-") for d in discovered
            if d.get("specialist") == specialist and d.get("approved") and d.get("has_db") and d.get("site")}


def await_sites(grid: GridClient, want: dict, deadline: float, discovered: list[dict]) -> list[dict]:
    """Re-run discovery inside this run until every wanted site is ready (an owner said y and the node
    came online) or the time budget ends. Saves queueing a new SuperGrid run for every check."""
    specialist, sites = want.get("specialist"), set(want.get("sites") or [])
    while not sites <= ready_sites(discovered, specialist) and time.monotonic() + AWAIT_POLL_S < deadline:
        time.sleep(AWAIT_POLL_S)
        nodes = grid.nodes()
        discovered = discover(grid, nodes) if nodes else []
        print(f"[bloom] waiting for {sorted(sites)}: ready {sorted(ready_sites(discovered, specialist))}")
    return discovered


def deliver(grid: GridClient, discovered: list[dict], proposal: dict, owner: str | None,
            sender: str, timeout: float = 60) -> dict:
    """Send a proposal to ONE inbox node of `owner` (the part after @ in the node name)."""
    def owner_of(d):
        name = str(d.get("node_name") or "")
        return name.split("@", 1)[1] if "@" in name else None

    targets = [d for d in discovered if d.get("inbox") and (not owner or owner_of(d) == owner)]
    if not targets:
        return {"ok": False, "error": f"no inbox node for owner {owner!r} answered discovery"}
    target = targets[0]
    pushed = grid.push([(target["node_id"], proposal_payload(proposal, sender))])
    mid = pushed[0].get("message_id") if pushed else None
    if not mid:
        return {"ok": False, "error": pushed[0].get("error") if pushed else "push failed"}
    replies, _ = grid.pull([mid], timeout)
    if not replies or not replies[0].get("payload"):
        return {"ok": False, "error": (replies[0].get("error") if replies else None) or "no reply from inbox node",
                "node_id": target["node_id"]}
    ack = json.loads(replies[0]["payload"])
    return {**{k: ack.get(k) for k in ("ok", "slug", "spec_sha256", "path", "error")},
            "node_id": target["node_id"], "node_name": target.get("node_name"), "message_id": mid}


def merge_roster(registry: list[dict], discovered: list[dict], have_nodes: bool) -> list[dict]:
    """Planner/routing roster: generalist + local (in-process) specialists + discovered, approved nodes.

    With zero nodes, fall back to the registry snapshot. Node-hosted registry entries that did not
    answer discovery are left out: the coordinator can't reach their data or approval.
    """
    if not have_nodes:
        return registry
    local = [a for a in registry if a.get("slug") == "generalist"
             or (a.get("kind") == "specialist" and not a.get("node_id"))]
    by_slug = {a["slug"]: dict(a) for a in local}
    for d in discovered:
        if not d.get("specialist") or not d.get("approved", True):
            continue
        site = d.get("site")
        key = f"{d['specialist']}@{str(site).strip().lower().replace(' ', '-')}" if site else d["specialist"]
        by_slug[key] = {
            "slug": key, "kind": "specialist", "category": d.get("category"), "site": site,
            "purpose": (f"{site}: " if site else "") + d.get("purpose", ""), "capabilities": d.get("tools", []),
            "node_id": d["node_id"], "node_name": d.get("node_name"), "has_db": d.get("has_db", False),
            "model": d.get("model"), "discovered": True,
        }
    return list(by_slug.values())


def execute(steps: list[Step], registry: list[dict], grid: GridClient, client, forced: str,
            step_timeout: float, emit=None, deadline: float | None = None,
            nodes: list[dict] | None = None) -> Orchestration:
    orch = Orchestration(steps[0].job_id if steps else "empty")
    fallback_reason: dict[str, str] = {}
    by_slug = {a["slug"]: a for a in registry}
    pending = list(steps)
    rr = [-1]
    deadline = deadline or (time.monotonic() + TIME_BUDGET_S)
    if nodes is None:
        nodes = grid.nodes() if forced != "inprocess" else []
        print(f"[bloom] {len(nodes)} SuperNode(s) available: {[n.get('name') or n.get('id') for n in nodes]}")

    while pending:
        ready = [s for s in pending if all(d in orch.outputs for d in s.depends_on)] or pending[:1]
        for s in ready:
            pending.remove(s)
            s.context = [{"from": orch.outputs[d].specialist, "output": orch.outputs[d].output}
                         for d in s.depends_on if d in orch.outputs]
            entry = by_slug.get(s.specialist, {"slug": s.specialist})
            s.spec = entry.get("spec")
        remote, local = [], []
        for s in ready:
            tier, node_id = _choose_tier(by_slug.get(s.specialist, {"slug": s.specialist}), nodes, forced, rr)
            (remote if node_id else local).append((s, tier, node_id))

        if remote and time.monotonic() < deadline:
            started = time.monotonic()
            try:
                results = grid.push([(node_id, s.to_payload()) for s, _, node_id in remote])
                id_map = {}
                for (s, tier, node_id), r in zip(remote, results):
                    if r.get("message_id"):
                        id_map[r["message_id"]] = (s, tier, node_id)
                        if emit:
                            emit("message", src="bloom", dst=s.specialist, node_id=node_id, text=s.instruction[:200])
                    else:
                        local.append((s, "inprocess", None))
                timeout = min(step_timeout, max(5.0, deadline - time.monotonic()))
                replies, _ = grid.pull(list(id_map), timeout) if id_map else ([], [])
                got = set()
                for m in replies:
                    s, tier, node_id = id_map.get(m.get("reply_to_message_id"), (None, None, None))
                    if s is None:
                        continue
                    got.add(m.get("reply_to_message_id"))
                    try:
                        res = Result.from_payload(m["payload"]) if m.get("payload") else None
                    except ValueError:
                        res = None
                    if res is None or not res.ok:
                        fallback_reason[s.step_id] = f"node {node_id}: " + ((res.error if res else None)
                                                                             or m.get("error") or "no result")[:160]
                        local.append((s, "inprocess", None))  # retry once in-process
                        continue
                    orch.outputs[s.step_id] = res
                    orch.record(s, tier, node_id, res, started, message_id=m.get("reply_to_message_id"))
                for mid, (s, _, node_id) in id_map.items():
                    if mid not in got:
                        fallback_reason[s.step_id] = f"node {node_id}: no reply before timeout"
                        local.append((s, "inprocess", None))
            except Exception as exc:  # noqa: BLE001 - Grid failure: degrade to in-process
                print(f"[bloom] Grid error ({exc}); running {len(remote)} step(s) in-process")
                local.extend((s, "inprocess", None) for s, _, _ in remote)
        else:
            local.extend((s, "inprocess", None) for s, _, _ in remote)

        for s, tier, _ in local:
            started = time.monotonic()
            if started > deadline:  # never risk SuperGrid's 5-minute task kill
                orch.record(s, "skipped", None, None, started, error="time budget exhausted")
                continue
            try:
                spec, post, _ = resolve_spec(s.specialist.split("@")[0], s.spec)
            except LookupError:
                spec, post, _ = resolve_spec("generalist", None)
            if emit:
                emit("message", src="bloom", dst=s.specialist, node_id=None, text=s.instruction[:200])
            res = run_spec(spec, s, client=client, postprocess=post)
            orch.outputs[s.step_id] = res
            orch.record(s, "inprocess", None, res, started, fallback=fallback_reason.get(s.step_id))
    return orch


def plan_run(agent, context, text: str, client=None) -> dict:
    """Planning as its own run (keeps each run under 5 min) -- but planned against what the Grid
    actually offers right now (discovery), so site-specific agents like X@hospital-a are visible."""
    job = parse_job(text)
    job = {**job, "mode": "plan", "job_id": job.get("job_id", "plan")}
    registry = load_registry(context)
    client = client or llm.runtime_client()
    model = str(context.run_config.get("bloom.orchestrator-model", "flwrlabs/endeavor-1.0"))
    grid = GridClient(agent.grid)
    nodes = grid.nodes()
    discovered = discover(grid, nodes) if nodes else []
    roster = merge_roster(registry, discovered, bool(nodes))
    print(f"[bloom] planning with roster: {[r['slug'] for r in roster]}")
    steps, missing = plan(job, roster, client, model)
    return {"model": model, "missing_capabilities": missing, "roster": [r["slug"] for r in roster],
            "steps": [{"step_id": s.step_id, "specialist": s.specialist, "instruction": s.instruction,
                       "depends_on": s.depends_on} for s in steps]}


def orchestrate(agent, context, text: str, client=None) -> dict:
    started = time.monotonic()
    job = parse_job(text)
    job.setdefault("job_id", f"j-{uuid.uuid4().hex[:8]}")
    registry = load_registry(context)
    client = client or llm.runtime_client()
    model = str(context.run_config.get("bloom.orchestrator-model", "flwrlabs/endeavor-1.0"))
    forced = str(context.run_config.get("bloom.routing", "auto"))
    step_timeout = float(context.run_config.get("bloom.step-timeout", 90))

    grid = GridClient(agent.grid)
    nodes = grid.nodes() if forced != "inprocess" else []
    print(f"[bloom] {len(nodes)} SuperNode(s) available: {[n.get('name') or n.get('id') for n in nodes]}")
    t_disc = time.monotonic()
    discovered = discover(grid, nodes) if nodes else []
    disc_ms = int((time.monotonic() - t_disc) * 1000)
    print(f"[bloom] discovery: {len(discovered)}/{len(nodes)} replied in {disc_ms}ms: "
          f"{[(d.get('specialist'), d.get('has_db'), d.get('approved')) for d in discovered]}")
    roster = merge_roster(registry, discovered, bool(nodes))
    if job.get("mode") == "deliver":  # Forge -> node owner's inbox, over the Grid
        res = deliver(grid, discovered, job.get("proposal") or {}, job.get("owner"), str(job.get("sender") or ""))
        if res.get("ok") and job.get("await"):  # keep watching in this same run instead of queueing new ones
            discovered = await_sites(grid, job["await"], started + AWAIT_BUDGET_S, discovered)
        return {"job_id": job["job_id"], "answer": "delivered" if res.get("ok") else res.get("error"),
                "output": json.dumps(res), "ok": bool(res.get("ok")), "steps": [], "missing_capabilities": [],
                "delivered": res, "discovered": discovered, "discovery_ms": disc_ms,
                "ms": int((time.monotonic() - started) * 1000)}
    if job.get("mode") == "describe":  # warm-up / smoke test: discovery only
        if job.get("await"):
            discovered = await_sites(grid, job["await"], started + AWAIT_BUDGET_S, discovered)
        return {"job_id": job["job_id"], "answer": f"{len(discovered)} of {len(nodes)} nodes replied",
                "output": json.dumps(discovered), "ok": bool(discovered) or not nodes, "steps": [],
                "missing_capabilities": [], "discovered": discovered, "discovery_ms": disc_ms,
                "ms": int((time.monotonic() - started) * 1000)}

    steps, missing = plan(job, roster, client, model)

    def emit(kind, **data):
        agent.events.emit({"type": f"bloom.{kind}", **data})

    orch = execute(steps, roster, grid, client, forced, step_timeout, emit,
                   deadline=started + TIME_BUDGET_S, nodes=nodes)
    by_id = {s.step_id: s for s in steps}
    for rec in orch.records:
        rec.instruction = by_id[rec.step_id].instruction[:300] if rec.step_id in by_id else ""
        out = orch.outputs.get(rec.step_id)
        rec.output_preview = (out.output if out else "")[:700]
    last = orch.outputs.get(steps[-1].step_id) if steps else None
    return {
        "job_id": job["job_id"],
        "answer": last.answer if last else None,
        "output": last.output if last else "",
        "ok": bool(last and last.ok),
        "steps": [r.__dict__ for r in orch.records],
        "missing_capabilities": missing,
        "discovered": discovered,
        "discovery_ms": disc_ms,
        "ms": int((time.monotonic() - started) * 1000),
    }
