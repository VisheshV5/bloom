"""Scan files for credential-looking strings before anything is published."""

from __future__ import annotations

import re
from pathlib import Path

PATTERNS = [
    ("openai-style key", re.compile(r"sk-[A-Za-z0-9_\-]{16,}")),
    ("aws key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assigned secret", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"][^'\"\s]{8,}['\"]")),
    ("bearer token", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.=]{20,}")),
]
TEXT_SUFFIXES = {".py", ".toml", ".md", ".json", ".jsonl", ".txt", ".yaml", ".yml", ".cfg", ".ini", ".html", ".js", ".sh", ".tmpl"}
SKIP_DIRS = {".venv", "__pycache__", ".git", "runs", "keys", ".pytest_cache", "node_modules"}
# Test fixtures deliberately contain fake keys.
ALLOW_FILES = {"tests/test_review_checks.py", "forge/secret_scan.py"}


def scan_text(text: str) -> list[str]:
    hits = []
    for label, pat in PATTERNS:
        for m in pat.finditer(text):
            hits.append(f"{label}: {m.group(0)[:10]}...")
    return hits


def scan_tree(root: Path) -> list[str]:
    hits = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not path.is_file():
            continue
        if str(rel) in ALLOW_FILES or path.suffix not in TEXT_SUFFIXES:
            continue
        for h in scan_text(path.read_text(errors="ignore")):
            hits.append(f"{rel}: {h}")
    return hits
