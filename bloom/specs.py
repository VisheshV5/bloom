"""Specialist spec schema, validation, and helpers shared by the app and the Forge."""

from __future__ import annotations

import re

from bloom.tools import TOOL_REGISTRY

ALLOWED_MODELS = [
    "openai/gpt-5.6-sol",
    "openai/gpt-6-luna",
    "openai/gpt-5.6-terra",
    "flwrlabs/endeavor-1.0",
    "dedicated/flowerai/Kimi-K2.7-Code-1OUHWL",
    "dedicated/flowerai/MiniMax-M3-OOLI9o",
]
DEFAULT_SPECIALIST_MODEL = "openai/gpt-5.6-sol"
MAX_INSTRUCTIONS = 2000
MAX_VERIFY = 600
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
RESERVED_SLUGS = {"bloom", "generalist", "orchestrator", "architect", "builder", "reviewer"}

SPEC_FIELDS = {
    "slug": str,
    "category": str,
    "purpose": str,
    "instructions": str,
    "model": str,
    "tools": list,
    "capabilities": list,
    "output_format": str,
    "version": int,
}


def module_name(slug: str) -> str:
    """Python module name for a specialist slug (sql-analyst -> sql_analyst)."""
    return slug.replace("-", "_")


def validate_spec(spec: dict) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems = []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]
    for name, typ in SPEC_FIELDS.items():
        if name not in spec:
            problems.append(f"missing field '{name}'")
        elif not isinstance(spec[name], typ) or (typ is int and isinstance(spec[name], bool)):
            problems.append(f"field '{name}' must be {typ.__name__}")
    if problems:
        return problems
    if not SLUG_RE.match(spec["slug"]) or len(spec["slug"]) > 40:
        problems.append("slug must be kebab-case, <= 40 chars")
    if spec["slug"] in RESERVED_SLUGS:
        problems.append(f"slug '{spec['slug']}' is reserved")
    if spec["model"] not in ALLOWED_MODELS:
        problems.append(f"model '{spec['model']}' not in allowed list")
    unknown = [t for t in spec["tools"] if t not in TOOL_REGISTRY]
    if unknown:
        problems.append(f"unknown tools: {unknown}")
    if not spec["instructions"].strip():
        problems.append("instructions are empty")
    if len(spec["instructions"]) > MAX_INSTRUCTIONS:
        problems.append(f"instructions longer than {MAX_INSTRUCTIONS} chars")
    if not all(isinstance(c, str) for c in spec["capabilities"]):
        problems.append("capabilities must be strings")
    verify = spec.get("verify", "")
    if not isinstance(verify, str) or len(verify) > MAX_VERIFY:
        problems.append(f"verify must be a string of at most {MAX_VERIFY} chars")
    return problems


def tool_catalog() -> list[dict]:
    """Tool names + descriptions, for the Architect's prompt."""
    return [{"name": t.name, "description": t.description} for t in TOOL_REGISTRY.values()]


# ── approval hashes (identical on the Forge and on the node) ──────────────────
HASH_FIELDS = ("slug", "category", "purpose", "instructions", "model", "tools", "examples", "verify",
               "postprocess_source")


def canonical_json(obj) -> str:
    import json

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def spec_hash(spec: dict) -> str:
    """sha256 of the canonical JSON of the spec fields that define behaviour.

    The node hashes the spec it is about to run (from the module in the FAB, or the payload),
    so any change to instructions/tools/examples/model produces a different, unapproved hash.
    """
    import hashlib

    core = {k: spec.get(k) for k in HASH_FIELDS}
    core["tools"] = list(core["tools"] or [])
    core["examples"] = [list(e) for e in (core["examples"] or [])]
    core["verify"] = core["verify"] or ""
    core["postprocess_source"] = (core["postprocess_source"] or "").strip()  # code that runs on the node
    return hashlib.sha256(canonical_json(core).encode()).hexdigest()


def spec_from_source(source: str) -> dict:
    """The same dict as bloom.specialists.spec_from_module, read from module source (no import)."""
    import ast

    values = {}
    tree = ast.parse(source)
    post = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "postprocess"), None)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return {"slug": values.get("SLUG"), "category": values.get("CATEGORY"), "purpose": values.get("PURPOSE", ""),
            "instructions": values.get("INSTRUCTIONS"), "model": values.get("MODEL"),
            "tools": list(values.get("TOOLS", [])), "examples": list(values.get("EXAMPLES", [])),
            "verify": values.get("VERIFY", ""),
            "postprocess_source": (ast.get_source_segment(source, post) or "") if post else ""}


def load_approved(path: str | None) -> set[str] | None:
    """Hashes the node owner approved. None = no approval file configured on this node."""
    import json
    from pathlib import Path

    if not path:
        return None
    p = Path(path).expanduser()
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text() or "[]")
    except ValueError:
        return set()
    if isinstance(data, dict):
        data = data.get("approved", data.get("hashes", []))
    out = set()
    for item in data if isinstance(data, list) else []:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict) and item.get("spec_sha256"):
            out.add(item["spec_sha256"])
    return out
