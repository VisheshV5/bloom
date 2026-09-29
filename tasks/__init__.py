"""Benchmark tasks and the final collaborative task."""

from __future__ import annotations

import json
from pathlib import Path

BENCHMARK = Path(__file__).with_name("benchmark.jsonl")


def load_benchmark(path: Path = BENCHMARK) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
