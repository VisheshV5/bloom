from evaluator.gaps import GapDetector
from forge.registry import Registry


def test_gap_fires_after_window_and_resets():
    d = GapDetector(threshold=0.6, window=5, min_attempts=5)
    fired = [d.record("generalist", "sql", ok) for ok in [False, True, False, False]]
    assert fired == [None] * 4
    gap = d.record("generalist", "sql", False)
    assert gap and gap.category == "sql" and gap.accuracy == 0.2 and gap.kind == "new"
    assert d.record("generalist", "sql", False) is None  # window cleared


def test_gap_not_flagged_when_passing_or_suppressed():
    d = GapDetector()
    assert all(d.record("generalist", "extraction", True) is None for _ in range(6))
    d.suppress("sql")
    assert all(d.record("generalist", "sql", False) is None for _ in range(6))


def test_specialist_underperforming_flags_improve():
    d = GapDetector()
    d.suppress("sql")
    gaps = [d.record("sql-analyst", "sql", False, is_specialist=True) for _ in range(5)]
    assert gaps[-1] and gaps[-1].kind == "improve"


def test_registry_add_reuse_and_scores(tmp_path):
    reg = Registry(tmp_path / "registry.json")
    assert [a["slug"] for a in reg.agents] == ["generalist"]
    spec = {"slug": "sql-analyst", "category": "sql", "purpose": "p", "instructions": "i", "model": "m",
            "tools": ["run_sql"], "capabilities": ["database"], "output_format": "", "version": 1}
    reg.add_specialist(spec, "bloom/specialists/sql_analyst.py", "vverm")
    assert reg.find_reusable("sql")["slug"] == "sql-analyst"
    assert reg.find_reusable(None, ["Database"])["slug"] == "sql-analyst"
    assert reg.find_reusable("stats") is None
    reg.record_score("sql-analyst", "sql", True)
    reg.record_score("sql-analyst", "sql", False)
    again = Registry(tmp_path / "registry.json")
    assert again.get("sql-analyst")["scores"]["sql"] == {"attempts": 2, "correct": 1, "recent": [1, 0]}
    snap = again.snapshot()
    assert {s["slug"] for s in snap} == {"generalist", "sql-analyst"}
