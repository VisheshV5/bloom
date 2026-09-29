"""Bloom: one Flower AgentApp, three kinds of roles.

- Grid message arrives on a SuperNode  -> specialist (replies via push_reply_message)
- bloom.mode = "orchestrate" (default) -> orchestrator on the SuperLink
- bloom.mode = architect|builder|reviewer|solve -> a Forge thinking job
Every non-specialist run prints exactly one `BLOOM_RESULT {json}` line for the local Forge.
"""

from __future__ import annotations

import json
import traceback

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

from bloom import forge_roles, llm, orchestrator, specialist
from bloom.protocol import parse_grid_prompt

RESULT_PREFIX = "BLOOM_RESULT "

app = AgentApp()


def input_text(agent: AgentSession, context: Context) -> str:
    # UNVERIFIED(U5): with `flwr run`, agent.prompt may be empty; the Forge passes bloom.input.
    configured = str(context.run_config.get("bloom.input", "") or "")
    return configured if configured.strip() else agent.prompt


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Dispatch to the right Bloom role."""
    grid_msg = parse_grid_prompt(agent.prompt)
    if grid_msg is not None:
        specialist.handle_grid_message(agent, context, grid_msg)
        return

    mode = str(context.run_config.get("bloom.mode", "orchestrate"))
    text = input_text(agent, context)
    try:
        if mode == "orchestrate":
            result = orchestrator.orchestrate(agent, context, text)
            summary = result["output"] or f"(no answer) {result}"
        elif mode == "plan":  # needs the Grid for discovery, so it lives with the orchestrator
            result = orchestrator.plan_run(agent, context, text)
            summary = json.dumps(result)[:4000]
        else:
            result = forge_roles.run(mode, text, context)
            summary = json.dumps(result)[:4000]
        result = {"mode": mode, "ok": True, **result}
    except Exception as exc:  # noqa: BLE001 - report failures to the Forge, then fail the run
        print(traceback.format_exc())
        print(RESULT_PREFIX + json.dumps({"mode": mode, "ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        raise
    print(RESULT_PREFIX + json.dumps(result, default=str))
    llm.emit_text(agent, summary)
