"""Check an agent's answer against a benchmark task."""

from __future__ import annotations

import re

_FINAL_RE = re.compile(r"FINAL:\s*(.+)", re.IGNORECASE)


def extract_final(text: str | None) -> str | None:
    """Return the text after the last `FINAL:` marker, or None."""
    if not text:
        return None
    matches = _FINAL_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip().strip("`*").strip()


def _norm(s: str) -> str:
    return " ".join(str(s).strip().strip(".").casefold().split())


def _number(s) -> float | None:
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"-?\d[\d,]*\.?\d*(?:[eE]-?\d+)?|-?\.\d+", str(s).replace("$", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _items(s) -> set[str]:
    return {_norm(x) for x in re.split(r"[,\n;]+", str(s)) if x.strip()}


def check(task: dict, answer) -> bool:
    if answer is None:
        return False
    kind = task.get("check", "exact")
    expected = task["answer"]
    if kind == "number":
        got = _number(answer)
        if got is None:
            return False
        tol = task.get("tolerance") or {"rel": 0.01}
        exp = float(expected)
        if "abs" in tol:
            return abs(got - exp) <= tol["abs"] + 1e-9
        return abs(got - exp) <= tol["rel"] * max(abs(exp), 1e-9)
    if kind == "set":
        return _items(answer) == _items(expected)
    if kind == "date":
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(answer))
        return bool(m) and m.group(0) == expected
    return _norm(answer) == _norm(expected)
