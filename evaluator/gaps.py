"""Rolling-window skill-gap detection."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class GapReport:
    category: str
    agent: str
    accuracy: float
    window: int
    kind: str = "new"  # "new" = no specialist yet, "improve" = specialist underperforming
    failures: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class GapDetector:
    def __init__(self, threshold: float = 0.6, window: int = 5, min_attempts: int = 5):
        self.threshold = threshold
        self.window = window
        self.min_attempts = min_attempts
        self._recent: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=window))
        self._failures: dict[tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=window))
        self._suppressed: set[str] = set()

    def suppress(self, category: str) -> None:
        """Stop flagging a category (a specialist is active or pending)."""
        self._suppressed.add(category)

    def unsuppress(self, category: str) -> None:
        self._suppressed.discard(category)

    def record(self, agent: str, category: str, correct: bool, task: dict | None = None,
               answer=None, is_specialist: bool = False) -> GapReport | None:
        key = (agent, category)
        self._recent[key].append(bool(correct))
        if not correct and task is not None:
            self._failures[key].append({"task_id": task.get("id"), "prompt": task.get("prompt"), "got": answer})
        recent = self._recent[key]
        if len(recent) < self.min_attempts:
            return None
        accuracy = sum(recent) / len(recent)
        if accuracy >= self.threshold:
            return None
        if not is_specialist and category in self._suppressed:
            return None
        report = GapReport(category, agent, accuracy, len(recent),
                           "improve" if is_specialist else "new", list(self._failures[key]))
        recent.clear()  # don't re-fire on the very next task
        return report

    def accuracy(self, agent: str, category: str) -> float | None:
        recent = self._recent.get((agent, category))
        return (sum(recent) / len(recent)) if recent else None
