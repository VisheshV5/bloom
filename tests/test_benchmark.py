from bloom.routing import classify
from evaluator.scorer import check, extract_final
from tasks import build_benchmark, final_task, load_benchmark


def test_benchmark_is_deterministic_and_matches_file():
    assert build_benchmark.build() == build_benchmark.build()
    assert load_benchmark() == build_benchmark.build()


def test_benchmark_shape_and_splits():
    tasks = load_benchmark()
    assert len(tasks) == 160
    assert {t["category"] for t in tasks} == set(build_benchmark.CATEGORIES)
    for c in build_benchmark.CATEGORIES:
        for diff, (n_dev, n_test) in {"standard": (8, 12), "hard": (4, 8)}.items():
            dev = [t for t in tasks if t["category"] == c and t["split"] == "dev" and t["difficulty"] == diff]
            test = [t for t in tasks if t["category"] == c and t["split"] == "test" and t["difficulty"] == diff]
            assert (len(dev), len(test)) == (n_dev, n_test), (c, diff)
        dev_p = {t["prompt"] for t in tasks if t["category"] == c and t["split"] == "dev"}
        test_p = {t["prompt"] for t in tasks if t["category"] == c and t["split"] == "test"}
        assert not dev_p & test_p
    assert len({t["id"] for t in tasks}) == len(tasks)
    for t in tasks:
        assert "FINAL:" in t["prompt"]
        assert check(t, t["answer"]), t["id"]  # the answer key passes its own check


def test_classifier_routes_every_benchmark_task():
    for t in load_benchmark():
        assert classify(t["prompt"]) == t["category"], t["id"]


def test_scorer_kinds():
    assert check({"answer": 10.0, "check": "number", "tolerance": {"abs": 0.1}}, "$10.05")
    assert not check({"answer": 10.0, "check": "number", "tolerance": {"abs": 0.01}}, "10.05")
    assert check({"answer": 1000, "check": "number", "tolerance": {"rel": 0.01}}, "1,005")
    assert check({"answer": "a, b", "check": "set"}, "b,a")
    assert check({"answer": "2026-01-02", "check": "date"}, "It is 2026-01-02.")
    assert check({"answer": "Palo Alto", "check": "exact"}, "palo alto.")
    assert not check({"answer": "x", "check": "exact"}, None)
    assert extract_final("blah\nFINAL: 42\nFINAL: `43`") == "43"


def test_final_task_reference_and_check():
    ref = final_task.reference()
    assert ref["significant"] and ref["change_pts"] < -3 and set(ref["per_hospital"]) == {"Hospital A", "Hospital B"}
    assert final_task.check(final_task.committee_note(ref), ref)
    assert not final_task.check("Readmissions went down a lot.", ref)
