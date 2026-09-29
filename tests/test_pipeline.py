import json

import pytest

import forge.pipeline as pipeline_mod
from evaluator.runner import Runner
from forge.approval import TerminalApprover
from forge.backends.mock import MockBackend
from forge.events import NullBus
from forge.nodes import NodeManager
from forge.pipeline import Forge
from forge.registry import Registry
from tasks import load_benchmark


@pytest.fixture
def stack(tmp_path, monkeypatch):
    spec_dir = tmp_path / "specialists"
    spec_dir.mkdir()
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(pipeline_mod, "SPECIALISTS_DIR", spec_dir)
    monkeypatch.setattr(pipeline_mod, "REGISTRY", reg_path)
    monkeypatch.setattr(pipeline_mod, "ROOT", tmp_path)
    bus = NullBus()
    registry = Registry(reg_path)
    backend = MockBackend(bus, speed=0)
    answers = []

    def make(auto=True, answer="y"):
        approver = TerminalApprover(auto=auto, input_fn=lambda q: answers.append(q) or answer,
                                    out=open("/dev/null", "w"))
        nodes = NodeManager("sim", bus=bus)
        return Forge(backend, registry, bus, approver, nodes, [t for t in load_benchmark() if t["split"] == "dev"], run_build=False)

    return make, registry, bus, spec_dir, backend


def test_forge_cycle_with_review_retry(stack):
    make, registry, bus, spec_dir, _ = stack
    out = make().grow({"category": "stats", "failures": []})
    assert out.outcome == "approved" and out.slug == "stats-analyst" and out.attempts == 2
    assert (spec_dir / "stats_analyst.py").exists()
    agent = registry.get("stats-analyst")
    assert agent["approved_by"] == "vverm" and agent["node"]["mode"] == "sim"
    stages = [e["stage"] for e in bus.events if e["type"] == "forge_stage"]
    assert "review_failed" in stages and stages[-1] == "done"


def test_rejection_writes_nothing(stack):
    make, registry, _, spec_dir, _ = stack
    out = make(auto=False, answer="n").grow({"category": "sql", "failures": []})
    assert out.outcome == "rejected" and not list(spec_dir.glob("*.py")) and registry.get("sql-analyst") is None


def test_reuse_instead_of_duplicate(stack):
    make, registry, _, _, _ = stack
    forge = make()
    assert forge.grow({"category": "sql", "failures": []}).outcome == "approved"
    assert forge.grow({"category": "sql", "failures": []}).outcome == "reused"
    assert sum(a["slug"] == "sql-analyst" for a in registry.agents) == 1


def test_auto_approve_refused_for_real_backends():
    with pytest.raises(ValueError):
        TerminalApprover(auto=True, backend_name="supergrid")


def test_full_mock_demo_grows_to_six_and_solves_final(stack):
    make, registry, bus, _, backend = stack
    runner = Runner(backend, registry, bus, make())
    bench = [t for t in load_benchmark() if t["split"] == "dev"]
    runner.run(bench, "round 1")
    runner.run(bench, "round 2")
    final = runner.run_final()
    slugs = {a["slug"] for a in registry.active()}
    assert slugs == {"generalist", "sql-analyst", "stats-analyst", "date-wrangler", "unit-converter", "report-writer"}
    assert final["passed"]
    assert not any(e["type"] == "gap_flagged" and e.get("category") == "extraction" for e in bus.events)
