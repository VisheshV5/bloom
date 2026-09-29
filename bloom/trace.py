"""Lightweight execution trace: every model call and tool call as a timed span.

Spans travel back to the orchestrator inside the specialist's Grid reply, so the dashboard
can draw a real timeline of what each agent did (no invented data).
"""

from __future__ import annotations

import time

MAX_SPANS = 40
PREVIEW = 180


def _clip(value, n: int = PREVIEW) -> str:
    text = value if isinstance(value, str) else str(value)
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


class Trace:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.spans: list[dict] = []
        self.tokens_in = 0
        self.tokens_out = 0
        self.model_calls = 0
        self.tool_calls = 0

    def _ms(self, t: float) -> int:
        return int((t - self.t0) * 1000)

    def model(self, model: str, start: float, end: float, response=None, phase: str = "") -> None:
        usage = getattr(response, "usage", None)
        tin = int(getattr(usage, "input_tokens", 0) or 0)
        tout = int(getattr(usage, "output_tokens", 0) or 0)
        self.tokens_in += tin
        self.tokens_out += tout
        self.model_calls += 1
        calls = [getattr(i, "name", None) for i in (getattr(response, "output", None) or [])
                 if getattr(i, "type", None) == "function_call"]
        self._add({"kind": "model", "name": model, "phase": phase, "start": self._ms(start), "end": self._ms(end),
                   "tokens_in": tin, "tokens_out": tout, "requested_tools": [c for c in calls if c][:6]})

    def tool(self, name: str, start: float, end: float, arguments, result: str, phase: str = "") -> None:
        self.tool_calls += 1
        self._add({"kind": "tool", "name": name, "phase": phase, "start": self._ms(start), "end": self._ms(end),
                   "args": _clip(arguments), "result": _clip(result), "error": '"error"' in (result or "")[:20]})

    def _add(self, span: dict) -> None:
        if len(self.spans) < MAX_SPANS:
            self.spans.append(span)

    def summary(self) -> dict:
        return {"tokens_in": self.tokens_in, "tokens_out": self.tokens_out, "model_calls": self.model_calls,
                "tool_calls": self.tool_calls, "ms": self._ms(time.monotonic())}
