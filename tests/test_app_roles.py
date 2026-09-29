import json

from bloom import agent_app, llm, orchestrator, specialist
from bloom.local_session import LocalAgent, LocalContext
from bloom.protocol import Result, Step, parse_grid_prompt
from tests.fakes import FakeClient, FakeSuperLinkGrid, NodeGrid

SQL_SPEC = {"slug": "sql-analyst", "kind": "specialist", "category": "sql", "purpose": "sql",
            "spec": {"slug": "sql-analyst", "model": "openai/gpt-5.6-sol", "tools": ["run_sql"],
                     "instructions": "Use run_sql. End with FINAL."}}
GENERALIST = {"slug": "generalist", "kind": "generalist", "category": None, "purpose": "any"}
SQL_TASK = "You have access to Bloom Coffee Co. sales data (SQLite). How many stores are there?"


def ctx(**cfg):
    return LocalContext({"bloom.registry": json.dumps([GENERALIST, SQL_SPEC]), **cfg})


def test_protocol_round_trip():
    from bloom.protocol import MAX_CONTEXT_CHARS

    s = Step("j1", "s1", "sql-analyst", "do it", [{"from": "x", "output": "y" * 20000}], spec={"a": 1})
    back = Step.from_payload(s.to_payload())
    assert back.instruction == "do it" and len(back.context[0]["output"]) == MAX_CONTEXT_CHARS and back.spec == {"a": 1}
    r = Result("j1", "s1", "sql-analyst", True, "out", "4")
    assert Result.from_payload(r.to_payload()) == r
    assert parse_grid_prompt('{"message_id":"1","src_node_id":"2","payload":"x"}')
    assert parse_grid_prompt("hello") is None


def test_tool_loop_executes_local_tools(coffee_db):
    calls = iter([[("run_sql", {"query": "SELECT COUNT(*) FROM patients"})], "FINAL: 1645"])
    client = FakeClient(lambda kw: next(calls))
    res = specialist.run_spec(SQL_SPEC["spec"], Step("j", "s1", "sql-analyst", SQL_TASK), client=client)
    assert res.ok and res.answer == "1645"
    tool_out = [i for i in client.requests[1]["input"] if i.get("type") == "function_call_output"]
    assert '"rows": [[1645]]' in tool_out[0]["output"]


def test_specialist_replies_once_even_on_failure():
    grid = NodeGrid()
    payload = Step("j", "s1", "sql-analyst", "q", spec=SQL_SPEC["spec"]).to_payload()
    msg = {"message_id": "m1", "src_node_id": "1", "payload": payload}
    res = specialist.handle_grid_message(LocalAgent(json.dumps(msg), grid=grid), LocalContext(), msg,
                                         client=FakeClient(raise_exc=RuntimeError("model down")))
    assert not res.ok and len(grid.replies) == 1
    assert "model down" in Result.from_payload(grid.replies[0]).error


def _run(grid, **cfg):
    client = FakeClient()
    agent = LocalAgent(json.dumps({"task": SQL_TASK, "mode": "single"}), grid=grid)

    def node_handler(node_agent, grid_msg):
        specialist.handle_grid_message(node_agent, LocalContext(), grid_msg, client=FakeClient())

    if isinstance(grid, FakeSuperLinkGrid) and grid.node_handler is None:
        grid.node_handler = node_handler
    return orchestrator.orchestrate(agent, ctx(**cfg), agent.prompt, client=client)


def test_tier3_inprocess_without_nodes():
    out = _run(FakeSuperLinkGrid([]))
    assert out["ok"] and out["answer"] == "42"
    assert out["steps"][0]["tier"] == "inprocess" and out["steps"][0]["specialist"] == "sql-analyst"


def test_tier2_payload_to_any_node():
    grid = FakeSuperLinkGrid([{"id": "111", "name": None, "location": None}])
    out = _run(grid)
    assert out["steps"][0]["tier"] == "payload" and out["steps"][0]["node_id"] == "111"
    step_msgs = [json.loads(m["payload"]) for m in grid.pushed if json.loads(m["payload"]).get("kind") == "step"]
    assert step_msgs[0]["spec"]["slug"] == "sql-analyst"
    assert json.loads(grid.pushed[0]["payload"])["kind"] == "describe"  # discovery first


def test_tier1_named_node():
    grid = FakeSuperLinkGrid([{"id": "7", "name": "other", "location": None},
                              {"id": "9", "name": "sql-analyst", "location": None}])
    out = _run(grid)
    assert out["steps"][0]["tier"] == "nodes" and out["steps"][0]["node_id"] == "9"


def test_silent_node_falls_back_inprocess():
    grid = FakeSuperLinkGrid([{"id": "5", "name": "sql-analyst", "location": None}], silent_nodes={"5"})
    out = _run(grid, **{"bloom.step-timeout": 0})
    assert out["ok"] and out["steps"][0]["tier"] == "inprocess"


def test_planner_multi_step_with_handoff():
    plan = {"steps": [{"step_id": "s1", "specialist": "sql-analyst", "instruction": "get data", "depends_on": []},
                      {"step_id": "s2", "specialist": "generalist", "instruction": "summarize", "depends_on": ["s1"]}],
            "missing_capabilities": [{"capability": "report-writer", "category": "writing", "why": "x"}]}
    def respond(kw):
        if "planner of Bloom" in str(kw.get("instructions")):
            return json.dumps(plan)
        if "Output from sql-analyst" in json.dumps(kw.get("input")):
            return "Summary.\nFINAL: four stores"
        return "rows\nFINAL: 4"  # sql step, and its self-check if the generated module has one

    client = FakeClient(respond)
    agent = LocalAgent(grid=FakeSuperLinkGrid([]))
    out = orchestrator.orchestrate(agent, ctx(), "How many stores? Write a note.", client=client)
    assert [s["specialist"] for s in out["steps"]] == ["sql-analyst", "generalist"]
    assert out["answer"] == "four stores" and out["missing_capabilities"][0]["capability"] == "report-writer"
    assert "Output from sql-analyst" in json.dumps(client.requests[-1]["input"])


def test_agent_app_prints_bloom_result(monkeypatch, capsys):
    monkeypatch.setattr(llm, "runtime_client", lambda: FakeClient())
    agent = LocalAgent("", grid=FakeSuperLinkGrid([]))
    agent_app.main(agent, ctx(**{"bloom.input": json.dumps({"task": SQL_TASK, "mode": "single"})}))
    line = [l for l in capsys.readouterr().out.splitlines() if l.startswith("BLOOM_RESULT ")][-1]
    result = json.loads(line[len("BLOOM_RESULT "):])
    assert result["ok"] and result["answer"] == "42" and result["mode"] == "orchestrate"
    assert agent.events.events[-1] == {"type": "response.completed"}


def test_agent_app_forge_role(monkeypatch, capsys):
    spec = {"slug": "x-analyst", "category": "x", "purpose": "p", "instructions": "FINAL", "model": "m",
            "tools": [], "capabilities": [], "output_format": "", "version": 1}
    monkeypatch.setattr(llm, "runtime_client", lambda: FakeClient(lambda kw: f"```json\n{json.dumps(spec)}\n```"))
    agent_app.main(LocalAgent(""), LocalContext({"bloom.mode": "architect", "bloom.input": json.dumps({"gap": {}})}))
    line = [l for l in capsys.readouterr().out.splitlines() if l.startswith("BLOOM_RESULT ")][-1]
    assert json.loads(line[13:])["spec"]["slug"] == "x-analyst"


def test_plan_role_then_orchestrate_with_given_plan():
    from bloom import forge_roles

    plan = {"steps": [{"step_id": "s1", "specialist": "sql-analyst", "instruction": "count", "depends_on": []}],
            "missing_capabilities": []}
    out = forge_roles.plan_only({"task": "How many stores?"}, ctx(), FakeClient(lambda kw: json.dumps(plan)))
    assert out["steps"][0]["specialist"] == "sql-analyst"
    client = FakeClient()
    job = {"task": "How many stores?", "mode": "plan", "job_id": "j", "plan": out["steps"]}
    res = orchestrator.orchestrate(LocalAgent(grid=FakeSuperLinkGrid([])), ctx(), json.dumps(job), client=client)
    assert res["ok"] and not any("planner of Bloom" in str(r.get("instructions")) for r in client.requests)
