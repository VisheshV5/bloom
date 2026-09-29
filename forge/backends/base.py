"""Backend protocol shared by mock, supergrid, and nebius."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class TaskResult:
    answer: str | None
    output: str = ""
    agent: str = "generalist"  # slug that produced the final answer
    ok: bool = True
    steps: list[dict] = field(default_factory=list)
    missing_capabilities: list[dict] = field(default_factory=list)
    error: str | None = None
    ms: int = 0


class LLMBackend(Protocol):
    name: str

    def architect(self, gap: dict, registry: list[dict]) -> dict:
        """Gap or capability request -> spec dict."""

    def builder(self, spec: dict, notes: list[str] | None, examples: list | None = None) -> dict:
        """Spec (+ notes, worked examples) -> {"instructions", "examples", "postprocess_body", "verify"}."""

    def reviewer_notes(self, spec: dict, source: str, results: dict) -> list[str]:
        """Human-readable notes for the Builder."""

    def run_task(self, task: dict, registry: list[dict], mode: str = "single") -> TaskResult:
        """Run a task through the orchestrator."""

    def run_with_spec(self, spec: dict, task: dict) -> TaskResult:
        """Run a task with a candidate spec (reviewer tests)."""

    def eval_batch(self, jobs: list[dict]) -> list[dict]:
        """Run eval jobs {arm, spec, task_id, prompt, rep} -> [{arm, task_id, rep, ok, answer, error}]."""
