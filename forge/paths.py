"""Project paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry.json"
RUNS = ROOT / "runs"
EVENTS = RUNS / "events.jsonl"
KEYS = ROOT / "keys"
SPECIALISTS_DIR = ROOT / "bloom" / "specialists"
TEMPLATE = ROOT / "templates" / "specialist_module.py.tmpl"
BACKUPS = RUNS / "backup"
PROPOSALS = RUNS / "proposals"
