"""Render a specialist module from a spec + Builder fields."""

from __future__ import annotations

import textwrap
from datetime import date

from forge.paths import TEMPLATE


def _indent_body(body: str) -> str:
    body = textwrap.dedent(body or "").strip("\n")
    if not body.strip():
        body = "return None"
    return textwrap.indent(body, "    ")


def render_module(spec: dict, fields: dict, approved_by: str = "pending") -> str:
    examples = [
        [str(e[0]), str(e[1])] for e in (fields.get("examples") or [])[:3]
        if isinstance(e, (list, tuple)) and len(e) == 2
    ]
    return TEMPLATE.read_text().format(
        purpose_doc=spec["purpose"].replace('"""', "'''"),
        date=date.today().isoformat(),
        version=spec.get("version", 1),
        approved_by=approved_by,
        slug=spec["slug"],
        category=spec["category"],
        purpose=spec["purpose"],
        model=spec["model"],
        tools=list(spec["tools"]),
        instructions=(fields.get("instructions") or spec["instructions"]).strip(),
        examples=examples,
        verify=(fields.get("verify") or spec.get("verify") or "").strip(),
        postprocess_body=_indent_body(fields.get("postprocess_body", "")),
    )
