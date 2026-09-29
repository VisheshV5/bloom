"""Reviewer's automated checks for a generated specialist module."""

from __future__ import annotations

import ast
import shutil
import subprocess
import tempfile
from pathlib import Path

from bloom.specs import ALLOWED_MODELS, module_name
from bloom.tools import TOOL_REGISTRY
from forge.paths import ROOT
from forge.secret_scan import scan_text

ALLOWED_IMPORTS = {"re", "json", "math", "statistics", "datetime", "decimal", "fractions",
                   "itertools", "collections"}
FORBIDDEN_NAMES = {"eval", "exec", "compile", "open", "__import__", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr", "input", "breakpoint", "exit", "quit"}
REQUIRED_NAMES = {"SLUG", "CATEGORY", "PURPOSE", "MODEL", "TOOLS", "INSTRUCTIONS", "EXAMPLES"}


def static_check(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(f"import of '{alias.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                problems.append(f"import from '{node.module}' is not allowed")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            problems.append(f"use of '{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            problems.append(f"dunder attribute access '{node.attr}' is not allowed")
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            problems.append(f"{type(node).__name__} is not allowed in a specialist module")
    for h in scan_text(source):
        problems.append(f"possible secret: {h}")
    return problems


def contract_check(source: str, spec: dict) -> list[str]:
    tree = ast.parse(source)
    values, problems = {}, []
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                problems.append(f"{node.targets[0].id} must be a literal")
    missing = REQUIRED_NAMES - values.keys()
    if missing:
        problems.append(f"missing module constants: {sorted(missing)}")
    if "postprocess" not in funcs or len(funcs["postprocess"].args.args) != 1:
        problems.append("missing `def postprocess(text)`")
    if values.get("SLUG") != spec["slug"]:
        problems.append("SLUG does not match the spec")
    if not isinstance(values.get("TOOLS"), list) or any(t not in TOOL_REGISTRY for t in values.get("TOOLS", [])):
        problems.append("TOOLS must be a list of allowlisted tool names")
    if values.get("MODEL") not in ALLOWED_MODELS:
        problems.append("MODEL is not in the allowed list")
    if "VERIFY" in values and not isinstance(values["VERIFY"], str):
        problems.append("VERIFY must be a string")
    if not isinstance(values.get("INSTRUCTIONS"), str) or "FINAL" not in values.get("INSTRUCTIONS", ""):
        problems.append("INSTRUCTIONS must tell the agent to end with `FINAL: <answer>`")
    return problems


def postprocess_check(source: str) -> list[str]:
    """Execute the (already statically checked) module and try postprocess on a sample."""
    namespace: dict = {}
    try:
        exec(compile(source, "<specialist>", "exec"), namespace)  # noqa: S102 - static-checked first
        got = namespace["postprocess"]("Some reasoning.\nFINAL: 42.5")
    except Exception as exc:  # noqa: BLE001
        return [f"postprocess raised {type(exc).__name__}: {exc}"]
    if str(got).strip() != "42.5":
        return [f"postprocess('...FINAL: 42.5') returned {got!r}, expected '42.5'"]
    return []


def build_check(source: str, slug: str) -> dict:
    """`flwr build` a temp copy of the app with the new module added."""
    holder = Path(tempfile.mkdtemp())
    tmp = holder / "bloom-review"  # Flower requires letters, digits, hyphens in the app dir name
    tmp.mkdir()
    try:
        shutil.copy2(ROOT / "pyproject.toml", tmp / "pyproject.toml")
        shutil.copy2(ROOT / "LICENSE", tmp / "LICENSE")
        shutil.copytree(ROOT / "bloom", tmp / "bloom", ignore=shutil.ignore_patterns("__pycache__"))
        (tmp / "bloom" / "specialists" / f"{module_name(slug)}.py").write_text(source)
        proc = subprocess.run(["uv", "run", "--project", str(ROOT), "flwr", "build", "--app", str(tmp)],
                              cwd=tmp, capture_output=True, text=True, timeout=180)
        ok = proc.returncode == 0 and any(tmp.glob("*.fab"))
        return {"ok": ok, "log": (proc.stdout + proc.stderr)[-1500:]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "log": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(holder, ignore_errors=True)
