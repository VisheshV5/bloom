"""Model access through Flower Runtime's OpenAI-compatible Responses endpoint."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from bloom.tools import call_tool, tool_schemas

# UNVERIFIED(U6): the runtime lists `instructions` as a recognized field. If it turns out to
# be ignored, flip this to "input" and instructions are sent as a leading developer message.
INSTRUCTIONS_MODE = "param"
MAX_TOOL_ROUNDS = 8  # Kimi on Nebius sometimes needs 5+ rounds for list-heavy answers


def runtime_client():
    """OpenAI client bound to the current AgentApp task (only works inside a Flower run)."""
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ["FLWR_RUNTIME_BASE_URL"],
        api_key=os.environ["FLWR_RUNTIME_API_KEY"],
        max_retries=0,
    )


def _as_items(input_: str | list) -> list:
    if isinstance(input_, str):
        return [{"type": "message", "role": "user", "content": input_}]
    return list(input_)


def _assistant_text(text: str, item_id: str | None = None) -> dict:
    """An assistant message in the full output-message shape strict providers (Nebius) validate."""
    import uuid

    return {"type": "message", "id": item_id or f"msg_{uuid.uuid4().hex}", "status": "completed",
            "role": "assistant", "content": [{"type": "output_text", "text": text, "annotations": []}]}


def sanitize(items: list) -> list:
    """Make replayed conversation items acceptable to strict providers (e.g. Nebius).

    Assistant messages must carry content as a list of output_text parts, and blank
    assistant messages are dropped (a plain-string ' ' content is rejected with a 400).
    """
    out = []
    for item in items:
        if isinstance(item, dict) and item.get("type") == "message" and item.get("role") == "assistant":
            content = item.get("content")
            if isinstance(content, str):
                if not content.strip():
                    continue
                item = _assistant_text(content, item.get("id"))
            elif isinstance(content, list):
                parts = [p for p in content if not (isinstance(p, dict) and p.get("type") == "output_text"
                                                    and not str(p.get("text", "")).strip())]
                if not parts:
                    continue
                item = {**item, "content": parts}
            if not item.get("id"):
                import uuid

                item = {**item, "id": f"msg_{uuid.uuid4().hex}"}
            item.setdefault("status", "completed")
        out.append(item)
    return out


def create(client, *, model: str, instructions: str, input: str | list, trace=None, phase: str = "",
           **kwargs) -> Any:
    items = sanitize(_as_items(input))
    start = time.monotonic()
    if INSTRUCTIONS_MODE == "input":
        items = [{"type": "message", "role": "developer", "content": instructions}, *items]
        response = client.responses.create(model=model, input=items, **kwargs)
    else:
        response = client.responses.create(model=model, instructions=instructions, input=items, **kwargs)
    if trace is not None:
        trace.model(model, start, time.monotonic(), response, phase)
    return response


def complete(client, *, model: str, instructions: str, input: str | list, **kwargs) -> str:
    return create(client, model=model, instructions=instructions, input=input, **kwargs).output_text


def run_tool_loop(client, *, model: str, instructions: str, input: str | list,
                  tool_names: list[str], max_rounds: int = MAX_TOOL_ROUNDS,
                  on_tool=None, return_items: bool = False, trace=None, phase: str = ""):
    """Let the model call Bloom's local tools for up to `max_rounds`, then return its text.

    With return_items=True, returns (text, items) where items is the full conversation
    (including tool calls/outputs and the final assistant message) for a follow-up turn.
    """
    items = _as_items(input)

    def done(text: str):
        if not return_items:
            return text
        if not items or items[-1].get("type") != "message" or items[-1].get("role") != "assistant":
            if text and text.strip():
                items.append(_assistant_text(text))
        return text, items

    def finish(text: str):
        # Some providers (seen with Kimi on Nebius) end a tool loop with blank text.
        # Ask once more, without tools, for the actual answer.
        if not (text or "").strip():
            text = complete(client, model=model, input=sanitize(items) + [
                {"type": "message", "role": "user",
                 "content": "Your last reply was empty. Using the tool results above, give your complete "
                            "answer now, ending with a line `FINAL: <answer>`."}],
                instructions=instructions, trace=trace, phase=phase + ":retry", **no_more_tools)
        return done(text)

    tools = tool_schemas(tool_names)
    # Strict providers expect the tool list whenever the history contains tool calls, so final
    # "answer now" requests keep the tools but forbid calling them.
    no_more_tools = {"tools": tools, "tool_choice": "none"} if tools else {}
    if not tools:
        response = create(client, model=model, instructions=instructions, input=items, trace=trace, phase=phase)
        items.extend(item.to_dict() for item in response.output)
        return finish(response.output_text)
    for _ in range(max_rounds):
        response = create(client, model=model, instructions=instructions, input=items,
                          tools=tools, tool_choice="auto", trace=trace, phase=phase)
        output = [item.to_dict() for item in response.output]
        calls = [i for i in output if i.get("type") == "function_call"]
        items.extend(output)
        if not calls:
            return finish(response.output_text)
        for call in calls:
            t_tool = time.monotonic()
            result = call_tool(call.get("name", ""), call.get("arguments"))
            if trace is not None:
                trace.tool(call.get("name", ""), t_tool, time.monotonic(), call.get("arguments"), result, phase)
            if on_tool:
                on_tool(call.get("name"), call.get("arguments"), result)
            items.append({"type": "function_call_output", "call_id": call["call_id"], "output": result})
    text = complete(client, model=model, input=items,
                    instructions=instructions + " Tool budget exhausted: give your best final answer now.",
                    trace=trace, phase=phase + ":budget", **no_more_tools)
    return finish(text)


def extract_json(text: str) -> dict:
    """Leniently pull the first JSON object out of model text (handles ```json fences)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                candidates.append(text[start : i + 1])
                break
    for c in candidates:
        try:
            value = json.loads(c)
            if isinstance(value, dict):
                return value
        except ValueError:
            continue
    raise ValueError("No JSON object found in model output")


def emit_text(agent, text: str) -> None:
    """Publish AgentApp-generated text to Flower Chat (documented delta + completed pattern)."""
    agent.events.emit({"type": "response.output_text.delta", "delta": text})
    agent.events.emit({"type": "response.completed"})
