"""Brian's reframe: data stays on the owner's node, the owner approves, the coordinator discovers."""

import json

from bloom import orchestrator
from bloom.local_session import LocalAgent, LocalContext
from bloom.protocol import Capabilities, Result, Step, describe_payload
from bloom.specialist import handle_grid_message
from bloom.specialists import load_specialist, spec_from_module
from bloom.specs import spec_from_source, spec_hash
from tests.fakes import FakeClient, FakeSuperLinkGrid, NodeGrid

SLUG = "generalist"  # a module that always ships in the FAB


def _msg(payload):
    return {"message_id": "m1", "src_node_id": "1", "payload": payload}


def test_hash_is_canonical_and_detects_edits():
    spec = spec_from_module(load_specialist(SLUG))
    same = json.loads(json.dumps(spec))
    assert spec_hash(spec) == spec_hash(dict(reversed(list(same.items()))))
    assert spec_hash({**spec, "instructions": spec["instructions"] + " "}) != spec_hash(spec)
    assert spec_hash({**spec, "tools": ["run_sql"]}) != spec_hash(spec)


def test_forge_and_node_hash_the_same_module():
    from pathlib import Path

    import bloom.specialists as pkg

    src = (Path(pkg.__file__).parent / "generalist.py").read_text()
    assert spec_hash(spec_from_source(src)) == spec_hash(spec_from_module(load_specialist(SLUG)))


def test_node_refuses_unapproved_spec(tmp_path):
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps(["deadbeef"]))
    grid = NodeGrid()
    payload = Step("j", "s1", SLUG, "hi").to_payload()
    ctx = LocalContext(node_config={"bloom-specialty": SLUG, "bloom-approved": str(approved)})
    res = handle_grid_message(LocalAgent(json.dumps(_msg(payload)), grid=grid), ctx, _msg(payload),
                              client=FakeClient())
    assert not res.ok and res.error == "spec not approved on this node" and len(grid.replies) == 1


def test_node_runs_approved_spec(tmp_path):
    digest = spec_hash(spec_from_module(load_specialist(SLUG)))
    approved = tmp_path / "approved.json"
    approved.write_text(json.dumps([{"spec_sha256": digest}]))
    grid = NodeGrid()
    payload = Step("j", "s1", SLUG, "hi").to_payload()
    ctx = LocalContext(node_config={"bloom-specialty": SLUG, "bloom-approved": str(approved)})
    res = handle_grid_message(LocalAgent(json.dumps(_msg(payload)), grid=grid), ctx, _msg(payload),
                              client=FakeClient())
    assert res.ok and res.answer == "42"


def test_describe_reports_capabilities_and_db(tmp_path, coffee_db):
    grid = NodeGrid()
    ctx = LocalContext(node_config={"bloom-specialty": SLUG, "bloom-db": str(coffee_db),
                                    "bloom-node-name": "generalist@brian"})
    handle_grid_message(LocalAgent(grid=grid), ctx, _msg(describe_payload()))
    caps = Capabilities.from_payload(grid.replies[0])
    assert caps.specialist == SLUG and caps.has_db and caps.approved and caps.node_name == "generalist@brian"


def test_coordinator_discovers_nodes_and_ignores_unapproved(tmp_path):
    approved = tmp_path / "approved.json"
    approved.write_text("[]")

    def node(agent, msg):
        ok_node = msg["payload"] and agent is not None
        cfg = {"bloom-specialty": SLUG}
        if agent.grid and len(nodes_seen) % 2:  # second node: owner hasn't approved anything
            cfg["bloom-approved"] = str(approved)
        nodes_seen.append(1)
        handle_grid_message(agent, LocalContext(node_config=cfg), msg, client=FakeClient())

    nodes_seen: list = []
    grid = FakeSuperLinkGrid([{"id": "1", "name": "a@brian", "location": None},
                              {"id": "2", "name": "b@brian", "location": None}], node_handler=node)
    job = json.dumps({"task": "hello", "mode": "describe", "job_id": "d"})
    out = orchestrator.orchestrate(LocalAgent(job, grid=grid), LocalContext({}), job, client=FakeClient())
    assert len(out["discovered"]) == 2 and out["steps"] == []
    assert sorted(d["approved"] for d in out["discovered"]) == [False, True]
    roster = orchestrator.merge_roster([{"slug": "generalist", "kind": "generalist"}], out["discovered"], True)
    assert [r["node_id"] for r in roster if r.get("discovered")] == ["1"]


def test_merge_falls_back_to_registry_without_nodes():
    reg = [{"slug": "generalist"}, {"slug": "sql-analyst", "kind": "specialist", "node_id": "9"}]
    assert orchestrator.merge_roster(reg, [], have_nodes=False) == reg
    assert [r["slug"] for r in orchestrator.merge_roster(reg, [], have_nodes=True)] == ["generalist"]


def test_node_hosted_growth_writes_proposal_and_needs_owner(tmp_path, monkeypatch):
    import forge.pipeline as pipeline_mod
    from forge.activation import activate
    from forge.approval import TerminalApprover
    from forge.backends.mock import MockBackend
    from forge.events import NullBus
    from forge.nodes import NodeManager
    from forge.pipeline import Forge
    from forge.registry import Registry
    from tasks import load_benchmark

    for name, value in {"SPECIALISTS_DIR": tmp_path / "spec", "REGISTRY": tmp_path / "registry.json",
                        "ROOT": tmp_path, "PROPOSALS": tmp_path / "proposals"}.items():
        monkeypatch.setattr(pipeline_mod, name, value)
    (tmp_path / "spec").mkdir()
    asked = []
    approver = TerminalApprover(auto=False, input_fn=lambda q: asked.append(q) or "y", out=open("/dev/null", "w"))
    reg = Registry(tmp_path / "registry.json")
    bus = NullBus()
    forge = Forge(MockBackend(bus, speed=0), reg, bus, approver, NodeManager("node", federation="@vverm/bloom-team"),
                  [t for t in load_benchmark() if t["split"] == "dev"], run_build=False)
    out = forge.grow({"category": "sql", "failures": []})
    assert out.outcome == "proposed" and not asked  # nobody on the Forge laptop was asked
    proposal = json.loads((tmp_path / "proposals" / "sql-analyst.json").read_text())
    assert set(proposal) >= {"spec", "module_source", "spec_sha256", "reviewer_results", "dev_examples_used"}
    assert spec_hash(spec_from_source(proposal["module_source"])) == proposal["spec_sha256"]
    assert reg.get("sql-analyst")["status"] == "proposed" and reg.specialist_for("sql") is None

    nodes = [[{"node-id": "77", "owner-name": "brianhuang08", "status": "registered", "name": "sql-analyst@brian"}],
             [{"node-id": "77", "owner-name": "brianhuang08", "status": "online", "name": "sql-analyst@brian"}]]
    res = activate(reg, "sql-analyst", bus=bus, lister=lambda: nodes.pop(0), sleep=lambda s: None, timeout=5)
    agent = reg.get("sql-analyst")
    assert agent["status"] == "active" and agent["approved_by"] == "node-owner:brianhuang08"
    assert agent["node"] == {"mode": "node", "node_id": "77", "name": "sql-analyst@brian"} and res["warm_up"] is None
