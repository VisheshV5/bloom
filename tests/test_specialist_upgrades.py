import ast
import json

import pytest

import forge.pipeline as pipeline_mod
from bloom.protocol import Result, Step
from bloom.specialist import run_spec
from evaluator.eval import ALL_ARMS, arm_specs, run_eval
from forge.approval import TerminalApprover
from forge.backends.mock import CANNED_SPECS, MockBackend
from forge.events import NullBus
from forge.nodes import NodeManager
from forge.pipeline import Forge
from forge.registry import Registry
from forge.render import render_module
from forge.review_checks import contract_check, static_check
from tasks import load_benchmark
from tests.fakes import FakeClient

SPEC = {"slug": "calc-analyst", "model": "m", "tools": ["calculate"], "instructions": "Use calculate. FINAL",
        "verify": "Recompute with calculate."}


def test_self_check_can_correct_the_answer():
    replies = iter(["draft\nFINAL: 10", [("calculate", {"expression": "3*4"})], "checked\nFINAL: 12"])
    client = FakeClient(lambda kw: next(replies))
    res = run_spec(SPEC, Step("j", "s1", "calc-analyst", "What is 3*4?"), client=client)
    assert res.ok and res.answer == "12" and res.checked and res.changed
    check_turn = client.requests[1]["input"]
    assert any(i.get("role") == "user" and "Self-check" in str(i.get("content")) and "10" in str(i.get("content"))
               for i in check_turn)
    assert any(i.get("role") == "assistant" for i in check_turn)  # sees its own draft
    assert Result.from_payload(res.to_payload()).changed


def test_self_check_confirms_and_is_skipped_without_verify():
    client = FakeClient(lambda kw: "FINAL: 12")
    res = run_spec(SPEC, Step("j", "s1", "calc-analyst", "q"), client=client)
    assert res.checked and not res.changed and len(client.requests) == 2
    client = FakeClient(lambda kw: "FINAL: 12")
    res = run_spec({**SPEC, "verify": ""}, Step("j", "s1", "calc-analyst", "q"), client=client)
    assert not res.checked and len(client.requests) == 1


def test_every_task_has_a_worked_method():
    assert all(t["how"] for t in load_benchmark())


def test_forge_bakes_worked_examples_from_dev_failures_only(tmp_path, monkeypatch):
    spec_dir = tmp_path / "specialists"
    spec_dir.mkdir()
    monkeypatch.setattr(pipeline_mod, "SPECIALISTS_DIR", spec_dir)
    monkeypatch.setattr(pipeline_mod, "REGISTRY", tmp_path / "registry.json")
    monkeypatch.setattr(pipeline_mod, "ROOT", tmp_path)
    bus = NullBus()
    reg = Registry(tmp_path / "registry.json")
    dev = [t for t in load_benchmark() if t["split"] == "dev"]
    forge = Forge(MockBackend(bus, speed=0), reg, bus, TerminalApprover(auto=True, out=open("/dev/null", "w")),
                  NodeManager("sim", bus=bus), dev, run_build=False)
    failed = [t for t in dev if t["category"] == "sql"][:4]
    out = forge.grow({"category": "sql", "failures": [{"task_id": t["id"]} for t in failed]})
    assert out.outcome == "approved"
    src = (spec_dir / "sql_analyst.py").read_text()
    assert static_check(src) == [] and contract_check(src, reg.get("sql-analyst")["spec"]) == []
    consts = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(src).body
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    assert len(consts["EXAMPLES"]) == 3 and all("Method: run_sql(" in o for _, o in consts["EXAMPLES"])
    assert consts["VERIFY"].startswith("Re-derive")
    test_prompts = {t["prompt"] for t in load_benchmark() if t["split"] == "test"}
    assert not any(i in test_prompts for i, _ in consts["EXAMPLES"])


def test_rendered_module_exposes_verify():
    spec = {**CANNED_SPECS["units"], "model": "openai/gpt-5.6-sol", "output_format": "", "version": 1}
    src = render_module(spec, {"postprocess_body": "    return None", "examples": [["in", "out"]]})
    assert "VERIFY = 'Convert your answer back" in src and "EXAMPLES = [['in', 'out']]" in src


def test_ablation_arm(tmp_path, monkeypatch):
    import evaluator.eval as ev
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path / "eval")
    reg = Registry(tmp_path / "registry.json")
    spec = {**CANNED_SPECS["dates"], "model": "openai/gpt-5.6-sol", "output_format": "", "version": 1}
    reg.add_specialist(spec, "bloom/specialists/date_wrangler.py", "vverm")
    arms = arm_specs(reg, "dates", "openai/gpt-6-luna")
    assert arms["generalist_tools_check"]["verify"] and not arms["generalist_tools"].get("verify")
    assert arms["specialist"]["verify"] and arms["specialist"]["model"] == "openai/gpt-6-luna"
    report = run_eval(MockBackend(NullBus(), speed=0), reg, load_benchmark(), arms=ALL_ARMS)
    assert "vs_generalist_tools_check" in report["paired"]
    assert report["categories"]["dates"]["generalist_tools_check"]["n"] == 20


def test_blank_self_check_keeps_the_draft():
    replies = iter(["draft\nFINAL: 12", " ", " "])  # self-check blank, and its retry blank too
    res = run_spec(SPEC, Step("j", "s1", "calc-analyst", "q"), client=FakeClient(lambda kw: next(replies)))
    assert res.answer == "12" and not res.changed and "[self-check" not in res.output


def test_sanitize_assistant_messages_for_strict_providers():
    from bloom.llm import sanitize

    items = [{"type": "message", "role": "user", "content": "hi"},
             {"type": "message", "role": "assistant", "content": " "},
             {"type": "message", "role": "assistant", "content": "answer"},
             {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": " "}]}]
    out = sanitize(items)
    assert out[0]["content"] == "hi" and len(out) == 2
    assert out[1]["content"] == [{"type": "output_text", "text": "answer", "annotations": []}]
    assert out[1]["id"].startswith("msg_") and out[1]["status"] == "completed"


def test_blank_reply_after_tools_is_retried():
    replies = iter([[("calculate", {"expression": "6*7"})], " ", "The result is 42.\nFINAL: 42"])
    client = FakeClient(lambda kw: next(replies))
    res = run_spec({**SPEC, "verify": ""}, Step("j", "s1", "calc-analyst", "6*7?"), client=client)
    assert res.answer == "42" and "empty" in json.dumps(client.requests[-1]["input"])


def test_trace_records_model_and_tool_spans():
    replies = iter([[("calculate", {"expression": "6*7"})], "FINAL: 42"])
    res = run_spec({**SPEC, "verify": ""}, Step("j", "s1", "calc-analyst", "6*7?"), client=FakeClient(lambda kw: next(replies)))
    kinds = [s["kind"] for s in res.trace]
    assert kinds == ["model", "tool", "model"]
    tool = res.trace[1]
    assert tool["name"] == "calculate" and "6*7" in tool["args"] and "42" in tool["result"]
    assert res.usage["model_calls"] == 2 and res.usage["tool_calls"] == 1
    assert all(s["end"] >= s["start"] for s in res.trace)


def test_trace_survives_grid_payload_and_orchestrator_records_it():
    from bloom import orchestrator
    from bloom.local_session import LocalAgent, LocalContext
    from bloom.specialist import handle_grid_message
    from tests.fakes import FakeSuperLinkGrid

    def node(agent, msg):
        handle_grid_message(agent, LocalContext(), msg, client=FakeClient(lambda kw: "FINAL: 4"))

    grid = FakeSuperLinkGrid([{"id": "9", "name": "sql-analyst", "location": None}], node_handler=node)
    reg = [{"slug": "generalist", "kind": "generalist"},
           {"slug": "sql-analyst", "kind": "specialist", "category": "sql",
            "spec": {"slug": "sql-analyst", "model": "m", "tools": [], "instructions": "FINAL"}}]
    ctx = LocalContext({"bloom.registry": json.dumps(reg)})
    job = json.dumps({"task": "SQLite: how many stores?", "mode": "single", "job_id": "j"})
    out = orchestrator.orchestrate(LocalAgent(job, grid=grid), ctx, job, client=FakeClient())
    step = out["steps"][0]
    assert step["tier"] == "nodes" and step["message_id"] and step["trace"] and step["usage"]["model_calls"] >= 1
    assert 0 <= step["start_ms"] <= step["end_ms"]
