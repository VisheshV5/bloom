"""Forge "thinking" roles, each run as one short SuperGrid run by the local Forge.

architect: gap/capability -> specialist spec
builder:   spec (+ reviewer notes) -> module fields (instructions, examples, postprocess body)
reviewer:  spec + source + check results -> notes
solve:     spec + task -> answer (reviewer's test tasks)
"""

from __future__ import annotations

import json

from bloom import llm
from bloom.protocol import Step
from bloom.specialist import run_spec
from bloom.specs import ALLOWED_MODELS, tool_catalog

ARCHITECT = """You are the Architect in Bloom's Forge. The team keeps failing a category of
tasks (or needs a missing capability). Design ONE new specialist agent.
Rules: pick tools only from the tool catalog; pick the model from the allowed list;
instructions must be concrete (<= 1500 chars), tell the agent to use its tools rather than
guess, and to end every reply with a line `FINAL: <answer>`. Also write `verify` (<= 400
chars): a category-specific way to independently double-check an answer with the tools
(e.g. "re-run the query with a different aggregation", "recompute with calculate").
slug is short kebab-case (e.g. "sql-analyst"). Reply with JSON only:
{"slug":"...","category":"...","purpose":"...","instructions":"...","verify":"...","model":"...",
 "tools":["..."],"capabilities":["..."],"output_format":"...","version":1}"""

BUILDER = """You are the Builder in Bloom's Forge. Turn the spec into the fields of a Python
specialist module. You may sharpen the instructions and the verify step using the worked
examples (tasks the team failed, with correct methods); they are added to the module
automatically, so do not repeat them. Write the BODY of `def postprocess(text):` (indented 4 spaces, stdlib `re` is
already imported; no other imports; no eval/exec/open) that returns the short final answer
string, usually the text after the last `FINAL:`. If reviewer notes are given, fix every
point. Reply with JSON only:
{"instructions":"...","verify":"...","postprocess_body":"    ..."}"""

REVIEWER = """You are the Reviewer in Bloom's Forge. Given a specialist spec, its generated
module source, and automated check results (static checks, build, test tasks), write
concrete, actionable notes for the Builder. Reply with JSON only:
{"verdict":"pass"|"fail","notes":["..."]}"""


def _model(context) -> str:
    """Forge roles use bloom.forge-model (fast); Endeavor stays the orchestrator's planner."""
    return str(context.run_config.get("bloom.forge-model", "openai/gpt-5.6-sol"))


def _json_call(client, model: str, instructions: str, prompt: str) -> dict:
    """Ask for JSON; if the reply isn't parseable, ask once more for only the JSON object."""
    text = llm.complete(client, model=model, instructions=instructions, input=prompt)
    try:
        return llm.extract_json(text)
    except ValueError:
        retry = [{"type": "message", "role": "user", "content": prompt},
                 {"type": "message", "role": "assistant", "content": text},
                 {"type": "message", "role": "user",
                  "content": "That was not valid JSON. Reply with ONLY the JSON object, no prose, no code fences."}]
        return llm.extract_json(llm.complete(client, model=model, instructions=instructions, input=retry))


def architect(job: dict, context, client) -> dict:
    prompt = json.dumps({
        "gap": job.get("gap"),
        "current_team": job.get("registry", []),
        "tool_catalog": tool_catalog(),
        "allowed_models": ALLOWED_MODELS,
    })
    return {"spec": _json_call(client, _model(context), ARCHITECT, prompt)}


def builder(job: dict, context, client) -> dict:
    prompt = json.dumps({"spec": job.get("spec"), "reviewer_notes": job.get("notes") or [],
                         "worked_examples": job.get("examples") or []})
    return {"fields": _json_call(client, _model(context), BUILDER, prompt)}


def reviewer(job: dict, context, client) -> dict:
    prompt = json.dumps({"spec": job.get("spec"), "source": job.get("source"), "results": job.get("results")})
    return _json_call(client, _model(context), REVIEWER, prompt)


def solve(job: dict, context, client) -> dict:
    spec = job["spec"]
    step = Step(job.get("job_id", "solve"), "s1", spec.get("slug", "candidate"), job["task"])
    res = run_spec(spec, step, client=client)
    return {"ok": res.ok, "output": res.output, "answer": res.answer, "error": res.error}


EVAL_TIME_BUDGET_S = 200
JOB_PREFIX = "BLOOM_JOB "


def eval_batch(job: dict, context, client) -> dict:
    """Run many (arm spec, task) jobs in parallel inside one run; stays under the 5-min task limit."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    deadline = time.monotonic() + float(job.get("budget_s", EVAL_TIME_BUDGET_S))

    def one(j: dict) -> dict:
        base = {"arm": j["arm"], "task_id": j["task_id"], "rep": j.get("rep", 0)}
        if time.monotonic() > deadline:
            return {**base, "ok": False, "answer": None, "error": "time budget exhausted"}
        step = Step("eval", str(j["task_id"]), j["spec"].get("slug", j["arm"]), j["prompt"])
        res = run_spec(j["spec"], step, client=client)
        out = {**base, "ok": res.ok, "answer": res.answer, "error": res.error, "usage": res.usage,
               "checked": res.checked, "changed": res.changed}
        # Stream each result immediately: if the run is killed at the 5-minute limit,
        # the Forge still recovers every job that finished.
        print(JOB_PREFIX + json.dumps(out, default=str), flush=True)
        return out

    with ThreadPoolExecutor(max_workers=int(job.get("workers", 6))) as pool:
        results = list(pool.map(one, job.get("jobs", [])))
    return {"results": results}


def plan_only(job: dict, context, client) -> dict:
    """Endeavor plans a multi-step task (its own run), so execution gets a full 5-minute budget."""
    from bloom import orchestrator

    registry = orchestrator.load_registry(context)
    model = str(context.run_config.get("bloom.orchestrator-model", "flwrlabs/endeavor-1.0"))
    job = {**job, "mode": "plan", "job_id": job.get("job_id", "plan")}
    steps, missing = orchestrator.plan(job, registry, client, model)
    return {"model": model, "missing_capabilities": missing,
            "steps": [{"step_id": s.step_id, "specialist": s.specialist, "instruction": s.instruction,
                       "depends_on": s.depends_on} for s in steps]}


ROLES = {"architect": architect, "builder": builder, "reviewer": reviewer, "solve": solve,
         "eval_batch": eval_batch, "plan": plan_only}


def run(mode: str, text: str, context, client=None) -> dict:
    if mode not in ROLES:
        raise ValueError(f"Unknown bloom.mode {mode!r}")
    job = json.loads(text) if text.strip() else {}
    return ROLES[mode](job, context, client or llm.runtime_client())
