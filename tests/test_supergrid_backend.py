import json

from forge.backends.supergrid import SuperGridBackend, overrides_for, parse_result
from forge.events import NullBus
from forge.nodes import NodeManager


def test_overrides_carry_mode_and_registry():
    o = overrides_for("orchestrate", [{"slug": "generalist"}], {"bloom.routing": "auto"}, {"task": "t"})
    assert o["bloom.mode"] == "orchestrate" and json.loads(o["bloom.input"]) == {"task": "t"}
    assert json.loads(o["bloom.registry"]) == [{"slug": "generalist"}] and o["bloom.routing"] == "auto"


def test_parse_result_takes_last_line():
    out = 'noise\nBLOOM_RESULT {"a": 1}\nmore\nBLOOM_RESULT {"a": 2}\n'
    assert parse_result(out) == {"a": 2}
    assert parse_result("nothing") is None


def test_dry_run_records_request():
    be = SuperGridBackend(NullBus(), federation="@vverm/bloom", dry_run=True, connection="local-agent")
    res = be._run("solve", {"task": "x"})
    assert res["dry_run"]
    req = be.last_request
    assert req["connection"] == "local-agent" and req["prompt"].startswith("[bloom:solve]")
    assert req["overrides"]["bloom.mode"] == "solve" and json.loads(req["overrides"]["bloom.input"]) == {"task": "x"}


def test_node_manager_plans_and_never_runs_without_approval():
    nm = NodeManager("node", confirm=lambda q: False, federation="@vverm/bloom")
    cmds = nm.planned_commands("sql-analyst")
    assert any("supernode register keys/sql-analyst.pub supergrid --name sql-analyst" in c for c in cmds)
    assert any("federation add-supernode" in c for c in cmds)
    assert any("bloom-specialty=\"sql-analyst\"" in c for c in cmds)
    sim = NodeManager("sim").join("sql-analyst")
    assert sim["mode"] == "sim" and sim["name"] == "sql-analyst"
