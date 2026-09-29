"""Task classification and specialist selection (deterministic, no model call)."""

from __future__ import annotations

import re

# Ordered: first match wins. `sql` first (its prompts mention revenue etc.), `extraction`
# before `dates` (extraction prompts may contain ISO dates).
_RULES: list[tuple[str, list[str]]] = [
    ("sql", [r"sqlite", r"sales data", r"\bsql\b", r"\bdatabase\b", r"\brevenue\b"]),
    ("extraction", [r"\bextract\b", r"\blist (every|all|the|only)\b", r"hashtags?", r"\bskus?\b"]),
    ("dates", [r"business days?", r"day of the week", r"calendar days", r"\b(mon|tues|wednes|thurs|fri|satur|sun)days\b",
               r"what date is", r"on what date", r"\b(mon|tues|wednes|thurs|fri|satur|sun)day of\b",
               r"full weeks", r"\bnet-\d+", r"due date"]),
    ("units", [r"\bconvert\b", r"per kilogram", r"fahrenheit", r"celsius", r"km/h", r"millilit",
               r"per lit", r"square cent", r"per mile", r"\bpace\b", r"\bmph\b", r"square f(oo|ee)t", r"\bpounds?\b", r"per ounce", r"\bgrams?\b", r"\bounces?\b|\boz\b", r"\bgallons?\b"]),
    ("stats", [r"standard deviation", r"\bmedian\b", r"t-test", r"t statistic", r"percentile",
               r"correlation", r"least-squares", r"interquartile", r"coefficient of variation", r"z-score", r"\bslope\b", r"\bmean\b", r"p-value"]),
    ("writing", [r"\bwrite\b.*\b(note|summary|memo|report)\b", r"\bsummari[sz]e\b"]),
]
_COMPILED = [(cat, [re.compile(p, re.I) for p in pats]) for cat, pats in _RULES]


def classify(text: str) -> str | None:
    for category, patterns in _COMPILED:
        if any(p.search(text) for p in patterns):
            return category
    return None


def pick_agent(category: str | None, registry: list[dict]) -> dict:
    """Active specialist for the category, else the generalist."""
    if category:
        for a in registry:
            if a.get("kind") == "specialist" and a.get("category") == category:
                return a
    return next((a for a in registry if a.get("slug") == "generalist"),
                {"slug": "generalist", "kind": "generalist", "category": None})
