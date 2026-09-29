"""Load KEY=VALUE pairs from the gitignored ~/bloom/.env (values are never printed or logged)."""

from __future__ import annotations

import os
from pathlib import Path

from forge.paths import ROOT

ENV_FILE = ROOT / ".env"


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def node_env() -> dict[str, str]:
    """Environment for SuperNode processes: the current env plus .env (which wins)."""
    return {**os.environ, **load_env()}


def describe() -> str:
    """Which variables are set, without revealing values."""
    env = load_env()
    return ", ".join(f"{k}={'set' if v else 'empty'}" for k, v in env.items()) or "no .env file"
