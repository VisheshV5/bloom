"""Text extraction helpers."""

from __future__ import annotations

import re


def regex_findall(pattern: str, text: str) -> list[str]:
    """Unique matches in order of first appearance (whole match if the pattern has groups)."""
    seen, out = set(), []
    for m in re.finditer(pattern, text):
        value = m.group(0)
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
