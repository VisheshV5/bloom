import json

import pytest

from bloom import forge_roles
from bloom.local_session import LocalContext
from evaluator.eval import arm_specs, run_eval, sign_test_p, summarize, wilson
from forge.backends.mock import CANNED_SPECS, MockBackend
from forge.events import NullBus
from forge.registry import Registry
from tasks import load_benchmark
from tests.fakes import FakeClient


def test_wilson_and_sign_test():
    lo, hi = wilson(12, 12)
    assert hi == 1.0 and 0.7 < lo < 0.8
    lo, hi = wilson(6, 12)
    assert lo < 0.5 < hi
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(10, 0) == pytest.approx(2 / 1024)
    assert sign_test_p(5, 5) == 1.0


def test_summarize_pairs_by_task_and_repeat():
    rows = []
    for i in range(4):
        rows += [{"task_id": f"t{i}", "rep": 0, "category": "sql", "arm": "specialist", "correct": True},
                 {"task_id": f"t{i}", "rep": 0, "category": "sql", "arm": "generalist_tools", "correct": i < 1},
                 {"task_id": f"t{i}", "rep": 0, "category": "sql", "arm": "generalist", "correct": False}]
    rep = summarize(rows, ["sql"])
    p = rep["paired"]["vs_generalist_tools"]
    assert (p["wins"], p["losses"], p["ties"], p["delta"]) == (3, 0, 1, 0.75)
    assert rep["overall"]["specialist"]["acc"] == 1.0


def _registry_with(tmp_path, categories):
    reg = Registry(tmp_path / "registry.json")
    for c in categories:
        spec = {**CANNED_SPECS[c], "model": "openai/gpt-5.6-sol", "output_format": "", "version": 1}
        reg.add_specialist(spec, f"bloom/specialists/{spec['slug']}.py", "vverm")
    return reg


def test_arms_use_same_model_and_fair_tools(tmp_path):
    reg = _registry_with(tmp_path, ["sql"])
    arms = arm_specs(reg, "sql", "openai/gpt-6-luna")
    assert {a["model"] for a in arms.values()} == {"openai/gpt-6-luna"}
    assert arms["generalist"]["tools"] == []
    assert set(arms["specialist"]["tools"]) <= set(arms["generalist_tools"]["tools"])
    assert "no tools" not in arms["generalist_tools"]["instructions"]
    assert arm_specs(reg, "stats", "m")["specialist"] is None


def test_mock_eval_uses_only_test_split(tmp_path, monkeypatch):
    import evaluator.eval as ev
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path / "eval")
    reg = _registry_with(tmp_path, ["sql", "stats"])
    report = run_eval(MockBackend(NullBus(), speed=0), reg, load_benchmark(), repeats=2)
    test_ids = {t["id"] for t in load_benchmark() if t["split"] == "test"}
    assert {r["task_id"] for r in report["results"]} == test_ids
    assert report["simulated"] and report["covered"] == ["sql", "stats"]
    assert report["categories"]["sql"]["specialist"]["n"] == 40  # (12 standard + 8 hard) x 2 repeats
    assert report["categories"]["dates"]["specialist"]["n"] == 0
    assert (tmp_path / "eval" / "latest.json").exists()


def test_eval_batch_role_runs_jobs_in_parallel():
    client = FakeClient(lambda kw: "FINAL: 7")
    jobs = [{"arm": a, "spec": {"slug": a, "model": "m", "tools": [], "instructions": "x FINAL"},
             "task_id": f"t{i}", "prompt": "q", "rep": 0} for i in range(5) for a in ("generalist", "specialist")]
    out = forge_roles.eval_batch({"jobs": jobs, "workers": 4}, LocalContext(), client)["results"]
    assert len(out) == 10 and all(r["answer"] == "7" and r["ok"] for r in out)
    assert len(client.requests) == 10


def test_bootstrap_ci_and_cost(tmp_path, monkeypatch):
    import evaluator.eval as ev
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path / "eval")
    reg = _registry_with(tmp_path, ["sql", "dates"])
    report = run_eval(MockBackend(NullBus(), speed=0), reg, load_benchmark(), repeats=1)
    p = report["paired"]["vs_generalist_tools"]
    lo, hi = p["delta_ci"]
    assert lo <= p["delta"] <= hi
    assert set(report["difficulty"]) == {"standard", "hard"}
    assert report["cost"]["generalist_tools"]["tokens"] > report["cost"]["generalist"]["tokens"]
    assert 0 <= report["cost"]["specialist"]["self_check_rate"] <= 1


def test_bootstrap_resamples_tasks_not_repeats():
    from evaluator.eval import bootstrap_delta_ci
    rows = [{"task_id": f"t{i}", "arm": a, "correct": a == "specialist" or i % 2, "rep": r}
            for i in range(10) for a in ("specialist", "generalist_tools") for r in range(3)]
    lo, hi = bootstrap_delta_ci(rows, "specialist", "generalist_tools")
    assert 0 < lo <= 0.5 <= hi <= 1


def test_infra_failures_are_excluded_not_counted_wrong(tmp_path, monkeypatch):
    import evaluator.eval as ev
    monkeypatch.setattr(ev, "EVAL_DIR", tmp_path / "eval")
    reg = _registry_with(tmp_path, ["sql"])
    backend = MockBackend(NullBus(), speed=0)
    real = backend.eval_batch

    def flaky(jobs):
        out = real(jobs)
        for r in out[1::4]:
            r.update(ok=False, answer=None, infra_error=True, error="missing from batch")
        return out

    backend.eval_batch = flaky
    tasks = [t for t in load_benchmark() if t["category"] == "sql"]
    report = run_eval(backend, reg, tasks)
    assert report["infra_errors"] > 0
    assert all(r["ok"] for r in report["results"])
    n = sum(v["n"] for v in report["categories"]["sql"].values() if isinstance(v, dict) and "n" in v)
    assert n == len(report["results"])


def test_partial_job_lines_are_recovered():
    from forge.backends.supergrid import parse_jobs
    out = 'noise\nBLOOM_JOB {"arm": "specialist", "task_id": "t1", "answer": "4", "ok": true}\nkilled'
    assert parse_jobs(out) == [{"arm": "specialist", "task_id": "t1", "answer": "4", "ok": True}]
