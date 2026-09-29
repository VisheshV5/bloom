from dashboard.story import before_after, build_story, display_name
from evaluator.runner import Runner
from tests.test_pipeline import stack  # noqa: F401 - fixture
from tasks import load_benchmark


def test_display_names():
    assert display_name("sql-analyst") == "SQL Analyst"
    assert display_name("date-wrangler") == "Date Wrangler"


def test_story_follows_the_demo(stack):  # noqa: F811
    make, registry, bus, _, backend = stack
    runner = Runner(backend, registry, bus, make())
    runner.run([t for t in load_benchmark() if t["split"] == "dev"], "round 1: practice")
    agents = {a["slug"]: a for a in registry.agents}
    seen = []
    for i in range(1, len(bus.events) + 1):
        seen.append(build_story(bus.events[:i], agents)["step"])
    assert {1, 2, 3, 4, 5} <= set(seen)
    pending = next(i for i, e in enumerate(bus.events) if e["type"] == "approval_pending")
    story = build_story(bus.events[: pending + 1], agents)
    assert story["step"] == 4 and "Waiting for a human" in story["headline"] and story["now"]["kind"] == "approval"
    assert story["now"]["icon"] != "🤖"
    final = runner.run_final()
    story = build_story(bus.events, {a["slug"]: a for a in registry.agents})
    assert final["passed"] and story["step"] == 6 and story["now"]["kind"] == "final"
    rows = {r["category"]: r for r in before_after(registry.agents)}
    assert rows["sql"]["after"] is not None and rows["extraction"]["after"] is None
