"""Append-only JSONL event bus consumed by the dashboard."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from forge.paths import EVENTS

EVENT_TYPES = {
    "agent_added", "agent_status", "message", "task_result", "gap_flagged", "forge_stage",
    "approval_pending", "approval_resolved", "node_joined", "published", "final_task",
    "phase", "error", "info", "eval_result", "trace", "proposal", "delivered", "waiting_owner",
}


class EventBus:
    def __init__(self, path: Path = EVENTS, echo: bool = False):
        self.path = path
        self.echo = echo
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._next_id = self._last_id() + 1

    def _last_id(self) -> int:
        if not self.path.exists():
            return 0
        last = 0
        with self.path.open() as f:
            for line in f:
                try:
                    last = max(last, int(json.loads(line)["id"]))
                except (ValueError, KeyError):
                    continue
        return last

    def emit(self, type_: str, **data) -> dict:
        if type_ not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type_!r}")
        with self._lock:
            event = {"id": self._next_id, "ts": time.time(), "type": type_, **data}
            self._next_id += 1
            with self.path.open("a") as f:
                f.write(json.dumps(event, default=str) + "\n")
        if self.echo:
            print(f"  [{type_}] " + ", ".join(f"{k}={v}" for k, v in data.items() if k != "spec")[:160])
        return event


def read_events(path: Path = EVENTS, since: int = 0) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("id", 0) > since:
                out.append(ev)
    return out


class NullBus(EventBus):
    """Event bus that records in memory only (tests)."""

    def __init__(self):  # noqa: D107 - no file
        self.events: list[dict] = []
        self._next_id = 1
        self._lock = threading.Lock()
        self.echo = False

    def emit(self, type_: str, **data) -> dict:
        event = {"id": self._next_id, "ts": time.time(), "type": type_, **data}
        self._next_id += 1
        self.events.append(event)
        return event
