"""Real backend: every call is one short AgentApp run of the local bloom project.

Runs are started like `flwr chat` does (StartRunRequest with a user_prompt), because
flwr 1.39's `flwr run` cannot start AgentApp runs ("A user prompt is required").
The JSON job goes in override_config (bloom.input) with mode/registry; the user prompt is a
short label (it becomes the conversation title). The app prints
one `BLOOM_RESULT {json}` line, which we read back with `flwr log <run-id>`.
Works against SuperGrid (`--connection supergrid`, after `flwr login supergrid`) or a
local SuperLink (`--connection local-agent`, see scripts/local_stack.sh).
"""

from __future__ import annotations

import json
import re
import time
import uuid

from forge.backends.base import TaskResult
from forge.flower_client import follow_logs, show_logs, start_agent_run
from forge.paths import RUNS

RESULT_RE = re.compile(r"BLOOM_RESULT (\{.*\})")
JOB_RE = re.compile(r"BLOOM_JOB (\{.*\})")


def parse_jobs(output: str) -> list[dict]:
    jobs = []
    for raw in JOB_RE.findall(output):
        try:
            jobs.append(json.loads(raw))
        except ValueError:
            continue
    return jobs
RUN_TIMEOUT_S = 420  # includes time queued on SuperGrid
DISCOVERY_FIELDS = ("specialist", "node_id", "node_name", "site", "has_db", "approved", "model", "inbox")
EVAL_BATCH_SIZE = 6  # jobs per AgentApp run, all in parallel: one wave stays well under 5 minutes
EVAL_PARALLEL_RUNS = 3


def parse_result(output: str) -> dict | None:
    matches = RESULT_RE.findall(output)
    for raw in reversed(matches):
        try:
            return json.loads(raw)
        except ValueError:
            continue
    return None


def overrides_for(mode: str, registry: list[dict], extra: dict | None = None, job: dict | None = None) -> dict:
    return {"bloom.mode": mode, "bloom.input": json.dumps(job) if job is not None else "",
            "bloom.registry": json.dumps(registry), **(extra or {})}


def prompt_for(mode: str, job: dict) -> str:
    """Short human-readable prompt (it becomes the run/conversation title); the job travels in bloom.input."""
    text = job.get("task") or job.get("prompt") or ""
    if mode == "orchestrate" and text:
        return text[:500]
    return f"[bloom:{mode}] {str(text)[:120]}".strip() if text else f"[bloom:{mode}] job"


class SuperGridBackend:
    name = "supergrid"
    has_data = False  # the coordinator never holds the data owner's database

    def __init__(self, bus, federation: str | None = None, dry_run: bool = False,
                 routing: str = "auto", orchestrator_model: str | None = None,
                 connection: str = "supergrid", **_):
        self.bus = bus
        self.federation = federation
        self.dry_run = dry_run
        self.connection = connection
        self.extra = {"bloom.routing": routing}
        if orchestrator_model:
            self.extra["bloom.orchestrator-model"] = orchestrator_model
        self.last_request: dict | None = None

    def _run(self, mode: str, job: dict, registry: list[dict] | None = None) -> dict:
        prompt = prompt_for(mode, job)
        overrides = overrides_for(mode, registry or [], self.extra, job)
        self.last_request = {"connection": self.connection, "federation": self.federation,
                             "prompt": prompt, "overrides": overrides}
        if self.dry_run:
            print(f"DRY RUN: start AgentApp run on '{self.connection}' mode={mode} prompt={prompt[:120]}")
            return {"ok": False, "error": "dry-run", "dry_run": True}
        started = time.monotonic()
        log_path = RUNS / "flwr" / f"{mode}-{uuid.uuid4().hex[:8]}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            run_id = start_agent_run(prompt, overrides, self.connection, self.federation)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"could not start run: {type(exc).__name__}: {exc}"}
        output = follow_logs(run_id, self.connection, timeout=RUN_TIMEOUT_S)
        result = parse_result(output)
        if result is None:  # logs may lag the run end
            output += "\n" + show_logs(run_id, self.connection)
            result = parse_result(output)
        log_path.write_text(output)
        if result is None and parse_jobs(output):  # run killed, but streamed jobs survived
            result = {"ok": False, "partial": True, "results": parse_jobs(output),
                      "error": "run ended without BLOOM_RESULT (partial results recovered)"}
        if result is None:
            tail = "\n".join(output.strip().splitlines()[-8:])
            result = {"ok": False, "error": f"No BLOOM_RESULT for run {run_id} (see {log_path}). Tail:\n{tail}"}
        result["run_id"] = run_id
        result["ms"] = int((time.monotonic() - started) * 1000)
        return result

    def deliver(self, proposal: dict, owner: str | None, sender: str = "vverm") -> dict:
        """Send a proposal over the Grid to the owner's inbox node (a short coordinator run)."""
        job = {"task": f"deliver {proposal.get('slug')}", "mode": "deliver", "proposal": proposal,
               "owner": owner, "sender": sender, "job_id": f"deliver-{proposal.get('slug')}"}
        res = self._run("orchestrate", job, [])
        return res.get("delivered") or {"ok": False, "error": res.get("error") or "no delivery result"}

    def describe(self, registry: list[dict]) -> dict:
        """Discovery-only run: every node answers describe. Doubles as warm-up for fresh nodes."""
        res = self._run("orchestrate", {"task": "describe", "mode": "describe", "job_id": "describe"}, registry)
        found = res.get("discovered") or []
        self.bus.emit("info", message=f"discovery: {len(found)} node(s) replied in {res.get('discovery_ms')}ms",
                      discovered=[{k: d.get(k) for k in DISCOVERY_FIELDS} for d in found])
        return res

    # ── Forge roles ────────────────────────────────────────────────────────
    def architect(self, gap: dict, registry: list[dict]) -> dict:
        res = self._run("architect", {"gap": gap, "registry": registry}, registry)
        if not res.get("spec"):
            raise RuntimeError(res.get("error") or "architect returned no spec")
        return res["spec"]

    def builder(self, spec: dict, notes: list[str] | None, examples: list | None = None) -> dict:
        res = self._run("builder", {"spec": spec, "notes": notes or [], "examples": examples or []})
        if not res.get("fields"):
            raise RuntimeError(res.get("error") or "builder returned no fields")
        return res["fields"]

    def reviewer_notes(self, spec: dict, source: str, results: dict) -> list[str]:
        res = self._run("reviewer", {"spec": spec, "source": source, "results": results})
        return [str(n) for n in res.get("notes", [])]

    # ── tasks ──────────────────────────────────────────────────────────────
    def run_task(self, task: dict, registry: list[dict], mode: str = "single") -> TaskResult:
        job = {"task": task["prompt"], "mode": task.get("mode", mode), "job_id": task.get("id")}
        self.bus.emit("message", src="forge", dst="bloom", node_id=None, text=task["prompt"][:140])
        planned_ms = None
        if job["mode"] == "plan":  # run 1: Endeavor plans; run 2: execute over the Grid
            planned = self._run("plan", job, registry)
            planned_ms = planned.get("ms")
            if planned.get("steps"):
                job["plan"] = planned["steps"]
                job["missing_capabilities"] = planned.get("missing_capabilities", [])
                self.bus.emit("info", message=f"Endeavor planned {len(planned['steps'])} steps in {planned.get('ms', 0) // 1000}s",
                              plan=[s["specialist"] for s in planned["steps"]])
        res = self._run("orchestrate", job, registry)
        steps = res.get("steps") or []
        for s in steps:
            self.bus.emit("message", src="bloom", dst=s.get("specialist"), node_id=s.get("node_id"),
                          tier=s.get("tier"), text=f"step {s.get('step_id')}")
            self.bus.emit("message", src=s.get("specialist"), dst="bloom", node_id=s.get("node_id"),
                          tier=s.get("tier"), text=f"FINAL: {s.get('answer')}")
        if res.get("discovered"):
            self.bus.emit("info", message=f"discovery: {len(res['discovered'])} node(s)",
                          discovered=[{k: d.get(k) for k in DISCOVERY_FIELDS} for d in res["discovered"]])
        if steps:
            self.bus.emit("trace", job_id=job["job_id"], run_id=res.get("run_id"), simulated=False,
                          total_ms=res.get("ms"), plan_ms=(planned_ms if job.get("plan") else None),
                          federation=self.federation, steps=steps)
        return TaskResult(
            answer=res.get("answer"), output=res.get("output", ""),
            agent=steps[-1]["specialist"] if steps else "generalist",
            ok=bool(res.get("ok")), steps=steps,
            missing_capabilities=res.get("missing_capabilities") or [],
            error=res.get("error"), ms=res.get("ms", 0),
        )

    def run_with_spec(self, spec: dict, task: dict) -> TaskResult:
        res = self._run("solve", {"spec": spec, "task": task["prompt"], "job_id": task.get("id")})
        return TaskResult(answer=res.get("answer"), output=res.get("output", ""), agent=spec["slug"],
                          ok=bool(res.get("ok")), error=res.get("error"), ms=res.get("ms", 0))

    def eval_batch(self, jobs: list[dict]) -> list[dict]:
        from concurrent.futures import ThreadPoolExecutor

        batches = [jobs[i:i + EVAL_BATCH_SIZE] for i in range(0, len(jobs), EVAL_BATCH_SIZE)]
        slim = lambda b: [{k: j[k] for k in ("arm", "spec", "task_id", "prompt", "rep")} for j in b]  # noqa: E731

        def run_batch(batch):
            res = self._run("eval_batch", {"jobs": slim(batch), "workers": EVAL_BATCH_SIZE})
            got = {(r["arm"], r["task_id"], r.get("rep", 0)): r for r in res.get("results", [])}
            return [got.get((j["arm"], j["task_id"], j.get("rep", 0)),
                            {"arm": j["arm"], "task_id": j["task_id"], "rep": j.get("rep", 0), "ok": False,
                             "answer": None, "infra_error": True,
                             "error": res.get("error") or "missing from batch"}) for j in batch]

        out: list[dict] = []
        with ThreadPoolExecutor(max_workers=EVAL_PARALLEL_RUNS) as pool:
            for i, rows in enumerate(pool.map(run_batch, batches), 1):
                out.extend(rows)
                self.bus.emit("info", message=f"eval batch {i}/{len(batches)} done")
        return out
