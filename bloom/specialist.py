"""Specialist worker: runs one step with a spec. Used on SuperNodes and in-process."""

from __future__ import annotations

import traceback
from typing import Callable

from bloom import llm
from bloom.grid_client import GridClient
from bloom.protocol import Capabilities, Result, Step, is_describe
from bloom.specialists import default_postprocess, load_specialist, spec_from_module
from bloom.specs import DEFAULT_SPECIALIST_MODEL, load_approved, spec_hash
from bloom.tools import sql
from bloom.trace import Trace

NODE_CONFIG_KEY = "bloom-specialty"
NODE_MODEL_KEY = "bloom-model"  # a node whose provider is e.g. Nebius must call that provider's model id
NODE_DB_KEY = "bloom-db"  # absolute path to the data owner's SQLite file (never in the FAB)
NODE_APPROVED_KEY = "bloom-approved"  # JSON list of spec_sha256 values the node owner approved
NODE_NAME_KEY = "bloom-node-name"


def resolve_spec(slug: str, payload_spec: dict | None, node_specialty: str | None = None
                 ) -> tuple[dict, Callable[[str], str | None], str]:
    """Pick the spec to run. Returns (spec, postprocess, source).

    Order: module shipped in the FAB for the requested slug -> spec sent in the payload.
    The node's configured specialty only labels the source (Tier 1) when it matches.
    """
    mod = load_specialist(slug)
    if mod is not None:
        source = "node-config" if node_specialty == slug else "module"
        return spec_from_module(mod), getattr(mod, "postprocess", default_postprocess), source
    if payload_spec and payload_spec.get("instructions"):
        return payload_spec, default_postprocess, "payload"
    raise LookupError(f"No spec available for specialist {slug!r}")


def build_input(step: Step) -> str:
    parts = [step.instruction.strip()]
    for c in step.context:
        parts.append(f"\n--- Output from {c.get('from', 'another agent')} ---\n{c.get('output', '')}")
    return "\n".join(parts)


SELF_CHECK = (
    "Self-check before you finish. Your draft final answer is: {answer}. {verify} "
    "Verify it independently with your tools; do not just restate your earlier work. "
    "If the draft is right, keep it; if it is wrong, correct it. End with `FINAL: <answer>`."
)
SELF_CHECK_ROUNDS = 3


def run_spec(spec: dict, step: Step, client=None, postprocess=default_postprocess, on_tool=None) -> Result:
    """Run one step: tool loop, then (if the spec has VERIFY + tools) a self-check pass.

    Never raises: failures become Result(ok=False).
    """
    trace = Trace()
    try:
        client = client or llm.runtime_client()
        instructions = spec["instructions"]
        examples = spec.get("examples") or []
        if examples:
            shots = "\n\n".join(f"Worked example input:\n{i}\nWorked example output:\n{o}" for i, o in examples[:3])
            instructions = f"{instructions}\n\n{shots}"
        model = spec.get("model") or DEFAULT_SPECIALIST_MODEL
        tools = list(spec.get("tools") or [])
        text, items = llm.run_tool_loop(client, model=model, instructions=instructions, input=build_input(step),
                                        tool_names=tools, on_tool=on_tool, return_items=True,
                                        trace=trace, phase="solve")
        answer = _safe_post(postprocess, text)
        checked = changed = False
        verify = (spec.get("verify") or "").strip()
        if verify and tools and answer is not None:
            items.append({"type": "message", "role": "user",
                          "content": SELF_CHECK.format(answer=answer, verify=verify)})
            text2 = llm.run_tool_loop(client, model=model, instructions=instructions, input=items,
                                      tool_names=tools, max_rounds=SELF_CHECK_ROUNDS, on_tool=on_tool,
                                      trace=trace, phase="self-check")
            answer2 = _safe_post(postprocess, text2)
            checked = True
            if answer2 is not None:
                changed = str(answer2).strip() != str(answer).strip()
                answer = answer2
            if text2 and text2.strip():  # a blank self-check reply never replaces a good answer
                text = f"{text}\n\n[self-check{' changed the answer' if changed else ' confirmed'}]\n{text2}"
        return Result(step.job_id, step.step_id, spec.get("slug", step.specialist), True, text, answer,
                      checked=checked, changed=changed, trace=trace.spans, usage=trace.summary(), model=model)
    except Exception as exc:  # noqa: BLE001
        return Result(step.job_id, step.step_id, step.specialist, False, "", None,
                      f"{type(exc).__name__}: {exc}", trace=trace.spans, usage=trace.summary())


def _safe_post(postprocess, text: str) -> str | None:
    """Final answer, or None if there isn't a usable one (blank counts as none)."""
    try:
        answer = postprocess(text)
    except Exception:  # noqa: BLE001 - generated postprocess must not kill the reply
        answer = default_postprocess(text)
    if answer is None or not str(answer).strip():
        answer = default_postprocess(text)
    return answer if answer is not None and str(answer).strip() else None


def capabilities(node_config: dict) -> Capabilities:
    """What this node offers: its configured specialist, tools actually usable here, DB, model."""
    from bloom.tools import available

    slug = node_config.get(NODE_CONFIG_KEY)
    node_model = node_config.get(NODE_MODEL_KEY)
    approved = load_approved(node_config.get(NODE_APPROVED_KEY))
    mod = load_specialist(str(slug)) if slug else None
    if mod is None:
        return Capabilities(specialist=None, model=str(node_model or ""), has_db=sql.available(),
                            node_name=node_config.get(NODE_NAME_KEY))
    spec = spec_from_module(mod)
    digest = spec_hash(spec)
    return Capabilities(
        specialist=spec["slug"], category=spec.get("category"), purpose=spec.get("purpose", ""),
        tools=[t for t in spec.get("tools", []) if available(t)], model=str(node_model or spec.get("model") or ""),
        has_db=sql.available(), node_name=node_config.get(NODE_NAME_KEY),
        approved=approved is None or digest in approved, spec_sha256=digest)


def handle_grid_message(agent, context, grid_msg: dict, client=None) -> Result:
    """SuperNode entry point: answer describe, or check approval, run the step, reply exactly once."""
    grid = GridClient(agent.grid)
    node_config = getattr(context, "node_config", None) or {}
    # UNVERIFIED(U2) on SuperGrid for Brian's nodes; verified locally and on vverm's nodes.
    sql.configure(node_config.get(NODE_DB_KEY))  # the data owner's file, if this node has one
    if is_describe(grid_msg.get("payload", "")):
        caps = capabilities(node_config)
        print(f"[bloom] describe -> specialist={caps.specialist} has_db={caps.has_db} approved={caps.approved}")
        grid.reply(caps.to_payload())
        return Result("describe", "describe", str(caps.specialist), True, "capabilities sent")
    try:
        step = Step.from_payload(grid_msg["payload"])
    except Exception as exc:  # noqa: BLE001
        result = Result("?", "?", "?", False, error=f"Bad payload: {exc}")
        grid.reply(result.to_payload())
        return result
    try:
        specialty = node_config.get(NODE_CONFIG_KEY)
        spec, post, source = resolve_spec(step.specialist, step.spec, str(specialty) if specialty else None)
        approved = load_approved(node_config.get(NODE_APPROVED_KEY))
        digest = spec_hash(spec)
        if approved is not None and digest not in approved:
            print(f"[bloom] REFUSED specialist={spec.get('slug')} sha256={digest[:12]}: not approved on this node")
            result = Result(step.job_id, step.step_id, step.specialist, False, error="spec not approved on this node")
            grid.reply(result.to_payload())
            return result
        node_model = node_config.get(NODE_MODEL_KEY)
        if node_model:
            spec = {**spec, "model": str(node_model)}
        print(f"[bloom] specialist={spec.get('slug')} source={source} model={spec.get('model')} "
              f"db={'yes' if sql.available() else 'no'} step={step.step_id}")
        result = run_spec(spec, step, client=client, postprocess=post)
    except Exception as exc:  # noqa: BLE001
        print(traceback.format_exc())
        result = Result(step.job_id, step.step_id, step.specialist, False, error=f"{type(exc).__name__}: {exc}")
    grid.reply(result.to_payload())
    return result
