"""Bloom dashboard server (stdlib only).

  uv run python -m dashboard.server [--port 8765]

GET /            -> index.html
GET /api/state   -> registry + scores + recent messages + approvals + forge status
GET /api/events?since=<id> -> raw events after id
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dashboard.story import before_after, build_story, display_name, icon, job, skill
from forge.events import read_events
from forge.paths import EVENTS, REGISTRY, RUNS

EVAL_LATEST = RUNS / "eval" / "latest.json"

HERE = Path(__file__).parent
FORGE_ROLES = ["architect", "builder", "reviewer"]
RECENT_MESSAGES = 40


def build_state() -> dict:
    try:
        registry = json.loads(REGISTRY.read_text())
    except (OSError, ValueError):
        registry = {"agents": [], "forge_log": []}
    events = read_events(EVENTS)

    messages, pending, forge_status = [], {}, {r: "idle" for r in FORGE_ROLES}
    forge_timeline: list[dict] = []
    phase, final, gaps, tiers = None, None, [], {}
    results = []
    for ev in events:
        t = ev["type"]
        if t == "message":
            messages.append({k: ev.get(k) for k in ("id", "ts", "src", "dst", "text", "node_id", "tier", "via")})
        elif t == "approval_pending":
            pending[ev["slug"]] = {k: ev.get(k) for k in ("slug", "purpose", "tools", "tests", "attempts", "ts")}
        elif t == "approval_resolved":
            pending.pop(ev["slug"], None)
        elif t == "agent_status" and ev.get("slug") in forge_status:
            forge_status[ev["slug"]] = ev.get("status", "idle")
        elif t == "forge_stage":
            if ev.get("stage") == "architect":
                forge_timeline = []
            forge_timeline.append({k: ev.get(k) for k in ("stage", "slug", "attempt", "notes", "ts", "category")})
        elif t == "phase":
            phase = ev.get("name")
        elif t == "final_task":
            final = {k: ev.get(k) for k in ("answer", "passed", "agents", "ts")}
        elif t == "gap_flagged":
            gaps.append({k: ev.get(k) for k in ("category", "accuracy", "kind", "capability", "ts")})
        elif t == "task_result":
            results.append(ev)
            tiers[ev.get("agent")] = ev.get("tier")

    agents = []
    for a in registry.get("agents", []):
        scores = a.get("scores", {})
        att = sum(s["attempts"] for s in scores.values())
        cor = sum(s["correct"] for s in scores.values())
        agents.append({
            "slug": a["slug"], "kind": a["kind"], "category": a.get("category"), "purpose": a.get("purpose"),
            "status": a.get("status"), "created_at": a.get("created_at"), "created_by": a.get("created_by"),
            "node": a.get("node"), "hub": a.get("hub"), "accuracy": (cor / att) if att else None,
            "attempts": att, "tier": tiers.get(a["slug"]),
            "tools": (a.get("spec") or {}).get("tools", []),
        })

    # generalist vs specialist accuracy per category
    by_cat: dict[str, dict] = {}
    for a in registry.get("agents", []):
        for cat, s in a.get("scores", {}).items():
            slot = by_cat.setdefault(cat, {"generalist": None, "specialist": None, "specialist_slug": None})
            acc = {"correct": s["correct"], "attempts": s["attempts"]}
            if a["kind"] == "generalist":
                slot["generalist"] = acc
            else:
                slot["specialist"] = acc
                slot["specialist_slug"] = a["slug"]

    evaluation = None
    try:
        raw = json.loads(EVAL_LATEST.read_text())
        evaluation = {k: raw.get(k) for k in ("categories", "overall", "paired", "headline", "simulated",
                                               "backend", "model", "repeats", "n_tasks", "n_runs", "seconds",
                                               "specialists", "created_at", "difficulty", "cost", "arms", "covered", "infra_errors")}
    except (OSError, ValueError):
        pass

    registry_agents = registry.get("agents", [])
    by_slug = {a["slug"]: a for a in registry_agents}
    team = [
        {"slug": a["slug"], "name": display_name(a["slug"]), "icon": icon(a.get("category"), a.get("kind")),
         "job": job(a), "kind": a["kind"], "skill": skill(a.get("category")) if a.get("category") else "Everything",
         "score": round(100 * a["accuracy"]) if a["accuracy"] is not None else None,
         "on_node": (a.get("node") or {}).get("mode") in {"node", "local", "sim"}}
        for a in agents if a["status"] == "active"
    ]
    traces = [ev for ev in events if ev["type"] == "trace"][-3:]
    return {
        "traces": traces,
        "story": build_story(events, by_slug),
        "team": team,
        "before_after": before_after(registry_agents),
        "eval": evaluation,
        "last_event_id": events[-1]["id"] if events else 0,
        "phase": phase,
        "agents": agents,
        "forge": {"status": forge_status, "timeline": forge_timeline[-12:]},
        "pending": list(pending.values()),
        "messages": messages[-RECENT_MESSAGES:],
        "scores": by_cat,
        "gaps": gaps[-10:],
        "final": final,
        "tasks_run": len(results),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send((HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path.startswith("/static/"):
            name = url.path.removeprefix("/static/")
            path = (HERE / "static" / name).resolve()
            types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
            if path.parent != (HERE / "static").resolve() or path.suffix not in types or not path.exists():
                self._send(b"not found", "text/plain", 404)
            else:
                self._send(path.read_bytes(), types[path.suffix])
        elif url.path == "/api/state":
            self._send(json.dumps(build_state(), default=str).encode(), "application/json")
        elif url.path == "/api/events":
            since = int(parse_qs(url.query).get("since", ["0"])[0])
            self._send(json.dumps(read_events(EVENTS, since)[-500:], default=str).encode(), "application/json")
        else:
            self._send(b"not found", "text/plain", 404)

    def log_message(self, *_args):  # quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Bloom dashboard: http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
