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


def test_replay_resets_to_generalist_and_replays_real_builds(tmp_path, monkeypatch):
    import dashboard.server as server
    import forge.paths as paths
    from forge.events import EventBus
    from forge.registry import Registry
    from forge.replay import replay

    events, reg_path = tmp_path / "events.jsonl", tmp_path / "registry.json"
    reg = Registry(reg_path)
    spec = {"slug": "sql-analyst", "category": "sql", "purpose": "p", "instructions": "i", "model": "m",
            "tools": ["run_sql"], "capabilities": [], "output_format": "", "version": 1}
    reg.add_specialist(spec, "x", "vverm")
    bus = EventBus(events)
    bus.emit("task_result", task_id="sql-01", category="sql", agent="generalist", correct=False, answer="?")
    bus.emit("forge_stage", stage="architect", category="sql")
    bus.emit("forge_stage", stage="builder", slug="sql-analyst", attempt=1)
    bus.emit("agent_added", slug="sql-analyst", category="sql", purpose="p", created_by=[])
    bus.emit("forge_stage", stage="architect", category="percentages")  # an abandoned build: skipped
    monkeypatch.setattr(server, "EVENTS", events)
    monkeypatch.setattr(server, "REGISTRY", reg_path)

    bus.emit("phase", name="session start")
    state = server.build_state()
    assert [a["slug"] for a in state["team"]] == ["generalist"] and state["story"]["step"] == 0

    done = replay(bus, reg, seconds_per_agent=0.01, pause=0, sleep=lambda s: None)
    state = server.build_state()
    assert done == ["sql-analyst"] and [a["slug"] for a in state["team"]] == ["generalist", "sql-analyst"]
    assert state["replay"] and not state["replay"]["live"]
    assert not any(e.get("category") == "percentages" for e in server.read_events(events) if e.get("replay"))
