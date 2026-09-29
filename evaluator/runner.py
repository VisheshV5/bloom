"""Run benchmark tasks through a backend, score them, and trigger the Forge on gaps."""

from __future__ import annotations

from collections import defaultdict

from evaluator.gaps import GapDetector
from evaluator.scorer import check
from tasks import final_task


def interleave(tasks: list[dict]) -> list[dict]:
    """Round-robin across categories so gaps show up at different moments."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for t in tasks:
        by_cat[t["category"]].append(t)
    out, i = [], 0
    while any(i < len(v) for v in by_cat.values()):
        for cat in by_cat:
            if i < len(by_cat[cat]):
                out.append(by_cat[cat][i])
        i += 1
    return out


class Runner:
    def __init__(self, backend, registry, bus, forge=None, detector: GapDetector | None = None):
        self.backend = backend
        self.registry = registry
        self.bus = bus
        self.forge = forge
        self.detector = detector or GapDetector()
        for a in registry.active():
            if a["kind"] == "specialist":
                self.detector.suppress(a["category"])

    def run_one(self, task: dict, round_label: str = "") -> tuple[bool, object]:
        result = self.backend.run_task(task, self.registry.snapshot())
        correct = check(task, result.answer)
        agent = result.agent if self.registry.get(result.agent) else "generalist"
        self.registry.record_score(agent, task["category"], correct)
        tier = (result.steps[-1].get("tier") if result.steps else None) or "inprocess"
        self.bus.emit("task_result", task_id=task["id"], category=task["category"], agent=agent,
                      correct=correct, answer=str(result.answer)[:80], expected=str(task["answer"])[:80],
                      tier=tier, round=round_label, error=result.error)
        is_spec = self.registry.get(agent)["kind"] == "specialist"
        gap = self.detector.record(agent, task["category"], correct, task, result.answer, is_specialist=is_spec)
        if gap and self.forge:
            self.bus.emit("gap_flagged", **{k: v for k, v in gap.to_dict().items() if k != "failures"})
            outcome = self.forge.grow(gap.to_dict())
            if outcome.outcome in {"approved", "reused"}:
                self.detector.suppress(task["category"])
        return correct, result

    def run(self, tasks: list[dict], round_label: str = "round 1", limit: int | None = None) -> dict:
        self.bus.emit("phase", name=round_label)
        ordered = interleave(tasks)[: limit or None]
        score: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for task in ordered:
            correct, _ = self.run_one(task, round_label)
            score[task["category"]][0] += int(correct)
            score[task["category"]][1] += 1
        summary = {c: f"{a}/{n}" for c, (a, n) in score.items()}
        self.bus.emit("info", message=f"{round_label} done", summary=summary)
        return summary

    def run_final(self, max_grow: int = 3) -> dict:
        self.bus.emit("phase", name="final task")
        task = final_task.TASK
        for _ in range(max_grow + 1):
            result = self.backend.run_task(task, self.registry.snapshot(), mode="plan")
            missing = [m for m in result.missing_capabilities
                       if not self.registry.find_reusable(m.get("category"), [m.get("capability", "")])]
            if missing and self.forge:
                for m in missing:
                    self.bus.emit("gap_flagged", category=m.get("category"), agent="planner",
                                  accuracy=None, kind="capability", capability=m.get("capability"))
                    self.forge.grow({"kind": "capability", "category": m.get("category"),
                                     "capability": m.get("capability"), "why": m.get("why"), "failures": []})
                continue
            passed = final_task.check(result.answer)
            self.bus.emit("final_task", answer=result.answer, passed=passed,
                          steps=result.steps, agents=[s.get("specialist") for s in result.steps])
            return {"answer": result.answer, "passed": passed, "steps": result.steps}
        return {"answer": None, "passed": False, "steps": []}
