import pytest

from forge.backends.mock import BAD_POSTPROCESS, GOOD_POSTPROCESS, CANNED_SPECS
from forge.render import render_module
from forge.review_checks import build_check, contract_check, postprocess_check, static_check
from forge.secret_scan import scan_text

SPEC = {**CANNED_SPECS["sql"], "model": "openai/gpt-5.6-sol", "output_format": "", "version": 1}


def render(body=GOOD_POSTPROCESS, **over):
    return render_module({**SPEC, **over}, {"postprocess_body": body})


def test_good_module_passes_all_checks():
    src = render()
    assert static_check(src) == [] and contract_check(src, SPEC) == [] and postprocess_check(src) == []


@pytest.mark.parametrize("body,needle", [
    (BAD_POSTPROCESS, "numpy"),
    ("    return eval(text)", "eval"),
    ("    return text.__class__", "__class__"),
    ("    import os\n    return os.getcwd()", "os"),
    ("    return open('/etc/passwd').read()", "open"),
])
def test_static_check_rejects(body, needle):
    problems = static_check(render(body))
    assert problems and any(needle in p for p in problems)


def test_planted_secret_is_caught():
    src = render(instructions="Use key sk-TESTTESTTESTTESTTEST to call things. FINAL")
    assert any("secret" in p for p in static_check(src))
    assert scan_text('api_key = "abcdefgh12345"')


def test_contract_rejects_unknown_tools_and_bad_postprocess():
    src = render(tools=["run_sql", "rm_rf"])
    assert any("TOOLS" in p for p in contract_check(src, SPEC))
    assert postprocess_check(render("    return 'nope'"))


@pytest.mark.slow
def test_build_check_builds_fab():
    assert build_check(render(), "sql-analyst")["ok"]
