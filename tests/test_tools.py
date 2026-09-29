import json

import pytest

from bloom.tools import call_tool, dates, sql, stats, units


def test_sql_is_read_only(coffee_db):
    assert "error" in json.loads(call_tool("run_sql", {"query": "DELETE FROM sales"}))
    assert "error" in json.loads(call_tool("run_sql", {"query": "SELECT 1; DROP TABLE sales"}))
    out = json.loads(call_tool("run_sql", {"query": "SELECT COUNT(*) FROM stores"}))
    assert out["result"]["rows"] == [[4]]


def test_welch_matches_reference_values():
    # Reference: scipy.stats.ttest_ind(a, b, equal_var=False) -> t=-2.02526, p=0.08210
    r = stats.ttest_welch([1, 2, 3, 4, 5, 6], [2, 4, 6, 8, 10, 13])
    assert r["t"] == pytest.approx(-2.02526, abs=1e-4)
    assert r["p_value"] == pytest.approx(0.08210, abs=1e-4)


def test_percentile_linear():
    assert stats.percentile([1, 2, 3, 4], 50) == 2.5
    assert stats.percentile(list(range(11)), 90) == pytest.approx(9.0)


def test_dates():
    assert dates.add_business_days("2026-03-06", 1) == "2026-03-09"  # Fri -> Mon
    assert dates.add_business_days("2026-03-09", -1) == "2026-03-06"
    assert dates.business_days_between("2026-03-06", "2026-03-13") == 5
    assert dates.weekday("2026-09-29") == "Tuesday"


def test_units():
    assert units.convert(1, "kg", "lb") == pytest.approx(2.20462, rel=1e-5)
    assert units.convert(212, "f", "c") == pytest.approx(100)
    with pytest.raises(ValueError):
        units.convert(1, "kg", "m")


def test_calculate_rejects_code():
    assert "error" in json.loads(call_tool("calculate", {"expression": "__import__('os')"}))
    assert json.loads(call_tool("calculate", {"expression": "sqrt(16) + 2**3"}))["result"] == 12.0


def test_sql_tool_absent_without_attached_db():
    from bloom.tools import tool_schemas

    sql.configure(None)
    assert [t["name"] for t in tool_schemas(["run_sql", "calculate"])] == ["calculate"]
    assert "not available" in json.loads(call_tool("run_sql", {"query": "SELECT COUNT(*) FROM stores"}))["error"]


def test_sql_refuses_row_level_queries(coffee_db):
    for q in ["SELECT * FROM sales", "SELECT s.* FROM stores s", "SELECT id, qty FROM sales",
              "SELECT a.id, * FROM sales a", "SELECT 1; DROP TABLE sales"]:
        assert "error" in json.loads(call_tool("run_sql", {"query": q})), q
    ok = json.loads(call_tool("run_sql", {"query": "SELECT date, SUM(qty) FROM sales GROUP BY date"}))["result"]
    assert ok["row_count"] == 181 and not ok["truncated"]
