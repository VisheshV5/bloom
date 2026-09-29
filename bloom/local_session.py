"""Minimal AgentSession/Context stand-ins to run Bloom roles outside Flower (tests, Nebius backend)."""

from __future__ import annotations

from typing import Any


class LocalEvents:
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)

    def get_trace(self) -> list[dict]:
        return []


class NoGrid:
    def tools(self) -> list[dict]:
        return []

    def call(self, tool_call: dict) -> dict:
        raise ValueError("No Grid outside a Flower run")


class LocalConnectors:
    def tools(self, names):
        return []

    def call(self, tool_call):
        raise ValueError("No connectors outside a Flower run")


class LocalAgent:
    def __init__(self, prompt: str = "", grid: Any = None):
        self.prompt = prompt
        self.events = LocalEvents()
        self.grid = grid or NoGrid()
        self.connectors = LocalConnectors()


class LocalContext:
    def __init__(self, run_config: dict | None = None, node_config: dict | None = None, run_id: int = 0):
        self.run_config = run_config or {}
        self.node_config = node_config or {}
        self.run_id = run_id
