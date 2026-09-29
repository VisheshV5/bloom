"""The ONLY module that touches `agent.grid`.

Grid tools (flwr 1.39, supercore/task_process/agent/grid.py):
  SuperLink side: get_nodes, push_messages, pull_messages
  SuperNode side: push_reply_message
We call them from code (not via the model) by building function_call items.
"""

from __future__ import annotations

import json
import uuid
from typing import Any


class GridUnavailable(RuntimeError):
    pass


class GridClient:
    def __init__(self, grid: Any):
        self._grid = grid
        try:
            self._tool_names = {t["name"] for t in grid.tools()}
        except Exception:  # noqa: BLE001 - no grid in this context
            self._tool_names = set()

    def has(self, name: str) -> bool:
        return name in self._tool_names

    def _call(self, name: str, **arguments) -> dict:
        if not self.has(name):
            raise GridUnavailable(f"Grid tool {name!r} is not available here")
        item = {
            "type": "function_call",
            "name": name,
            "call_id": f"bloom-{uuid.uuid4().hex[:12]}",
            "arguments": json.dumps(arguments),
        }
        out = self._grid.call(item)
        return json.loads(out["output"])

    def nodes(self) -> list[dict]:
        """[{id, name, location}] or [] if the Grid is unavailable."""
        try:
            return list(self._call("get_nodes", sample_size=None).get("nodes", []))
        except Exception:  # noqa: BLE001
            return []

    def push(self, messages: list[tuple[str, str]]) -> list[dict]:
        """messages: [(dst_node_id, payload)] -> [{message_id, error}] in order."""
        body = [{"dst_node_id": str(n), "payload": p, "reply_to_message_id": None} for n, p in messages]
        return list(self._call("push_messages", messages=body)["results"])

    def pull(self, message_ids: list[str], timeout: float) -> tuple[list[dict], list[str]]:
        out = self._call("pull_messages", message_ids=list(message_ids), timeout=max(0, min(300, timeout)))
        return list(out.get("messages", [])), list(out.get("pending_message_ids", []))

    def reply(self, payload: str) -> dict:
        """Node side: reply once to the instruction that started this task."""
        return self._call("push_reply_message", payload=payload)
