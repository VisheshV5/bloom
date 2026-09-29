"""registry.json: every agent in the team, who built it, and how well it scores."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from forge.paths import BACKUPS, REGISTRY, SPECIALISTS_DIR

RECENT_WINDOW = 10


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generalist_entry() -> dict:
    from bloom.specialists import generalist, spec_from_module

    spec = spec_from_module(generalist)
    return {
        "slug": "generalist",
        "kind": "generalist",
        "category": None,
        "purpose": generalist.PURPOSE,
        "spec": {k: spec[k] for k in ("model", "tools", "instructions")},
        "module": "bloom/specialists/generalist.py",
        "status": "active",
        "created_at": now_iso(),
        "created_by": ["human:vverm"],
        "approved_by": "vverm",
        "node": {"mode": "inprocess", "node_id": None, "name": None},
        "hub": None,
        "scores": {},
    }


def fresh_registry() -> dict:
    return {"version": 1, "agents": [generalist_entry()], "forge_log": []}


class Registry:
    def __init__(self, path: Path = REGISTRY):
        self.path = path
        if not path.exists():
            self.data = fresh_registry()
            self.save()
        else:
            self.data = json.loads(path.read_text())

    # ── persistence ────────────────────────────────────────────────────────
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".registry.", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(self.data, f, indent=2)
            f.write("\n")
        os.replace(tmp, self.path)

    def reload(self) -> None:
        self.data = json.loads(self.path.read_text())

    # ── queries ────────────────────────────────────────────────────────────
    @property
    def agents(self) -> list[dict]:
        return self.data["agents"]

    def get(self, slug: str) -> dict | None:
        return next((a for a in self.agents if a["slug"] == slug), None)

    def active(self) -> list[dict]:
        return [a for a in self.agents if a["status"] == "active"]

    def specialist_for(self, category: str) -> dict | None:
        return next((a for a in self.active() if a["kind"] == "specialist" and a["category"] == category), None)

    def find_reusable(self, category: str | None, capabilities: list[str] | None = None) -> dict | None:
        """An existing active specialist that already covers this category or capability."""
        caps = {c.lower() for c in (capabilities or [])}
        for a in self.active():
            if a["kind"] != "specialist":
                continue
            if category and a["category"] == category:
                return a
            if caps & {c.lower() for c in a["spec"].get("capabilities", [])}:
                return a
        return None

    def snapshot(self) -> list[dict]:
        """Compact view passed to the orchestrator via run-config."""
        return [
            {
                "slug": a["slug"],
                "kind": a["kind"],
                "category": a["category"],
                "purpose": a["purpose"],
                "capabilities": a["spec"].get("capabilities", []),
                "node_id": a["node"].get("node_id"),
                "node_name": a["node"].get("name"),
                "spec": {k: a["spec"].get(k) for k in ("model", "tools", "instructions", "verify")} | {"slug": a["slug"]},
            }
            for a in self.active()
        ]

    # ── mutations ──────────────────────────────────────────────────────────
    def add_specialist(self, spec: dict, module: str, approved_by: str | None, node: dict | None = None,
                       status: str = "active") -> dict:
        if self.get(spec["slug"]):
            raise ValueError(f"agent {spec['slug']} already exists")
        entry = {
            "slug": spec["slug"],
            "kind": "specialist",
            "category": spec["category"],
            "purpose": spec["purpose"],
            "spec": spec,
            "module": module,
            "status": status,
            "created_at": now_iso(),
            "created_by": ["architect", "builder", "reviewer"],
            "approved_by": approved_by,
            "node": node or {"mode": "inprocess", "node_id": None, "name": None},
            "hub": None,
            "scores": {},
        }
        self.agents.append(entry)
        self.save()
        return entry

    def activate(self, slug: str, node: dict, approved_by: str) -> dict:
        agent = self.get(slug)
        agent.update(status="active", node=node, approved_by=approved_by, activated_at=now_iso())
        self.save()
        return agent

    def proposed(self) -> list[dict]:
        return [a for a in self.agents if a["status"] == "proposed"]

    def set_node(self, slug: str, node: dict) -> None:
        self.get(slug)["node"] = node
        self.save()

    def set_hub(self, slug: str, hub: str) -> None:
        self.get(slug)["hub"] = hub
        self.save()

    def record_score(self, slug: str, category: str, correct: bool) -> None:
        agent = self.get(slug)
        if agent is None:
            return
        s = agent["scores"].setdefault(category, {"attempts": 0, "correct": 0, "recent": []})
        s["attempts"] += 1
        s["correct"] += int(bool(correct))
        s["recent"] = (s["recent"] + [int(bool(correct))])[-RECENT_WINDOW:]
        self.save()

    def log_forge(self, **entry) -> None:
        self.data["forge_log"].append({"ts": now_iso(), **entry})
        self.save()

    # ── reset ──────────────────────────────────────────────────────────────
    def reset(self) -> Path:
        """Back up registry + generated modules to runs/backup/<ts>/, then start fresh.

        Generated modules are moved (not deleted) so nothing is lost.
        """
        backup = BACKUPS / time.strftime("%Y%m%d-%H%M%S")
        backup.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            shutil.copy2(self.path, backup / "registry.json")
        for mod in SPECIALISTS_DIR.glob("*.py"):
            if mod.name not in {"__init__.py", "generalist.py"}:
                shutil.move(str(mod), backup / mod.name)
        self.data = fresh_registry()
        self.save()
        return backup
