"""Bloom dashboard server (stdlib only).

  uv run python -m dashboard.server [--port 8765]

GET /            -> index.html
GET /api/state   -> registry + scores + recent messages + approvals + forge status
GET /api/events?since=<id> -> raw events after id
"""

from __future__ import annotations

import argparse
import json
import os
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


LOCAL_OWNER = "vishesh"  # nodes registered from this laptop without an @owner suffix


def places(registry_agents: list[dict], nodes: dict, trace: dict | None) -> list[dict]:
    """Where each step of the latest team task ran: specialist, site, node id, and whose laptop."""
    owners = {}
    for a in registry_agents:
        node = a.get("node") or {}
        if node.get("node_id") and node.get("name"):
            name = str(node["name"])
            owners[str(node["node_id"])] = name.split("@", 1)[1] if "@" in name else LOCAL_OWNER
    owners.update({nid: d["owner"] for nid, d in nodes.items() if d.get("owner")})
    site_owner, local_slugs = {}, set()
    for f in (RUNS / "nodes" / "settings").glob("*.json"):
        try:
            cfg = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if cfg.get("site"):
            site_owner[str(cfg["site"]).lower().replace(" ", "-")] = str(cfg.get("name", "@" + LOCAL_OWNER)).split("@")[-1]
    try:
        local_slugs = set(json.loads((RUNS / "nodes" / "pids.json").read_text()))
    except (OSError, ValueError):
        pass
    out = []
    for st in (trace or {}).get("steps") or []:
        spec = str(st.get("specialist") or "")
        base, _, site = spec.partition("@")
        nid = str(st.get("node_id") or "") or None
        owner = owners.get(nid or "") or site_owner.get(site)
        if not owner and st.get("tier") == "nodes" and base in local_slugs:
            owner = LOCAL_OWNER
        out.append({"specialist": spec, "slug": base, "site": site or None, "node_id": nid,
                    "tier": st.get("tier"), "owner": owner})
    return out


def stage(events: list[dict]) -> str:
    """replay -> ready (replay finished, waiting for Continue) -> live."""
    phases = [e.get("name") for e in events if e["type"] == "phase"]
    if "live" in phases:
        return "live"
    if phases and phases[-1] == "replay done":
        return "ready"
    return "replay" if any(e.get("replay") for e in events) else "live"


HOSPITAL_OWNERS = {"hospital-a": "Brian", "hospital-b": "Vishesh"}


def _site(slug: str) -> str:
    return slug.replace("-", " ").title()


def activity(events: list[dict]) -> dict | None:
    """One plain sentence for what Bloom is doing right now in the live part, and since when.
    `waiting` is True while a hospital owner still has to approve (the garden grows a seedling)."""
    live = next((i for i, e in enumerate(events) if e["type"] == "phase" and e.get("name") == "live"), None)
    if live is None:
        return None
    text, since, waiting = "Starting the live run…", events[live]["ts"], False
    joined: list[str] = []
    for e in events[live + 1:]:
        t = e["type"]
        if t == "gap_flagged":
            text, since = "Bloom spotted a gap: no agent on the team can read patient records.", e["ts"]
        elif t == "proposal" or (t == "forge_stage" and e.get("stage") == "delivering"):
            text, since, waiting = ("Sending the hospital records agent to Brian's laptop over the Flower Grid, then "
                                    "waiting for him to read it and type y. Hospital B is Vishesh's and was approved "
                                    "earlier. (A Grid run can sit in SuperGrid's queue for a minute or two first.)"), e["ts"], True
        elif t == "delivered":
            text, since, waiting = ("Delivered. Waiting for Brian to read the agent's code and type y…", e["ts"], True) \
                if e.get("ok") else (f"Delivery failed: {e.get('error')}", e["ts"], False)
        elif t in ("node_joined", "waiting_owner") and e.get("site"):
            if t == "node_joined" and e["site"] not in joined:
                joined.append(e["site"])
            missing = [s for s in HOSPITAL_OWNERS if s not in joined]
            if missing:
                s0 = missing[0]
                text = f"{', '.join(_site(j) for j in joined)} joined. Waiting for {HOSPITAL_OWNERS[s0]} to approve {_site(s0)} on their laptop…"
                since, waiting = e["ts"], True
            else:
                text, since, waiting = "Both hospitals joined. Starting the question…", e["ts"], False
        elif t == "phase" and e.get("name") == "final task":
            text, since, waiting = ("Asking the question: the Coordinator plans which agents to use, then each hospital "
                                    "counts its own records and the Stats and Writing agents finish the answer "
                                    "(about 3–4 minutes)…"), e["ts"], False
        elif t == "final_task":
            return None
    return {"text": text, "since": since, "waiting": waiting}


def sites(events: list[dict]) -> dict[str, list[dict]]:
    """Per agent, the hospital sites whose nodes joined this session (one flower each)."""
    out: dict[str, list[dict]] = {}
    for e in events:
        if e["type"] == "node_joined" and e.get("site"):
            out.setdefault(e["slug"], [])
            if all(x["site"] != e["site"] for x in out[e["slug"]]):
                out[e["slug"]].append({"site": e["site"], "owner": e.get("owner"), "node_id": e.get("node_id")})
    return out


LIVE_LOG = RUNS / "live.log"
_live_proc = None


def start_live() -> tuple[int, dict]:
    """Continue button: start `python -m forge live` in the background (once)."""
    global _live_proc
    if _live_proc is not None and _live_proc.poll() is None:
        return 409, {"ok": False, "error": "already running"}
    import subprocess
    import sys

    log = open(LIVE_LOG, "w")
    _live_proc = subprocess.Popen([sys.executable, "-m", "forge", "live"], cwd=HERE.parent, stdout=log,
                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  start_new_session=True,  # restarting the dashboard must not kill the demo
                                  env={**os.environ, "PYTHONUNBUFFERED": "1"})  # live.log updates as it happens
    return 200, {"ok": True, "pid": _live_proc.pid, "log": str(LIVE_LOG)}


def last_question(events: list[dict]) -> str | None:
    """The full text of the latest team-task question (message text is shortened for the log)."""
    msg = next((e for e in reversed(events) if e["type"] == "message" and e.get("src") in ("forge", "user")), None)
    if not msg:
        return None
    if msg.get("question"):
        return msg["question"]
    from tasks.final_task import PROMPT  # older events only kept the first 140 characters
    text = str(msg.get("text") or "")
    return PROMPT if PROMPT.startswith(text) else text


def build_state() -> dict:
    try:
        registry = json.loads(REGISTRY.read_text())
    except (OSError, ValueError):
        registry = {"agents": [], "forge_log": []}
    all_events = read_events(EVENTS)
    # A presentation session starts from the Generalist alone: only events after the latest
    # "session start" drive the story, and only agents that joined since then are shown.
    session_id = max((e["id"] for e in all_events if e["type"] == "phase" and e.get("name") == "session start"),
                     default=None)
    events = [e for e in all_events if session_id is None or e["id"] >= session_id]
    joined_order = [e["slug"] for e in events if e["type"] in ("agent_added", "node_joined") and e.get("slug")]
    replay_events = [e for e in events if e.get("replay")]
    replay = None
    if replay_events:
        recorded = [e["recorded_ts"] for e in replay_events if e.get("recorded_ts")] or [replay_events[0]["ts"]]
        replay = {"from": min(recorded), "to": max(recorded),
                  "live": not events or not events[-1].get("replay")}

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
    if session_id is not None:  # generalist + agents that joined during this session, in join order
        order = {slug: i for i, slug in enumerate(dict.fromkeys(joined_order))}
        agents = sorted([a for a in agents if a["kind"] == "generalist" or a["slug"] in order],
                        key=lambda a: -1 if a["kind"] == "generalist" else order[a["slug"]])
        registry_agents = [a for a in registry_agents if a["kind"] == "generalist" or a["slug"] in order]
        by_slug = {a["slug"]: a for a in registry_agents}
    team = [
        {"slug": a["slug"], "name": display_name(a["slug"]), "icon": icon(a.get("category"), a.get("kind")),
         "job": job(a), "kind": a["kind"], "skill": skill(a.get("category")) if a.get("category") else "Everything",
         "score": round(100 * a["accuracy"]) if a["accuracy"] is not None else None,
         "on_node": (a.get("node") or {}).get("mode") in {"node", "local", "sim"}}
        for a in agents if a["status"] == "active"
    ]
    traces = [ev for ev in all_events if ev["type"] == "trace"][-3:]
    nodes: dict[str, dict] = {}  # node_id -> {specialist, node_name, site, owner, has_db} from the latest discovery
    for ev in all_events:
        for d in ev.get("discovered") or []:
            if d.get("node_id"):
                name = str(d.get("node_name") or "")
                nodes[str(d["node_id"])] = {**d, "owner": name.split("@", 1)[1] if "@" in name else "vishesh"}
    return {
        "replay": replay,
        "nodes": nodes,
        "question": last_question(all_events),
        "stage": stage(events),
        "activity": activity(events),
        "sites": sites(events),
        "places": places(registry.get("agents", []), nodes, traces[-1] if traces else None),
        "session": session_id is not None,
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

    def do_POST(self):  # noqa: N802
        # The custom header forces a CORS preflight (which this server never answers), so other
        # websites open in the same browser cannot press Continue.
        if urlparse(self.path).path != "/api/continue" or self.headers.get("X-Bloom") != "continue":
            self._send(b"not found", "text/plain", 404)
            return
        status, body = start_live()
        self._send(json.dumps(body).encode(), "application/json", status)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        dist = HERE / "dist"
        if url.path in ("/", "/index.html") and (dist / "index.html").exists():
            self._send((dist / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path in ("/", "/index.html", "/classic"):
            self._send((HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path.startswith("/assets/") and (dist / "assets").exists():
            path = (dist / url.path.lstrip("/")).resolve()
            types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
                     ".woff2": "font/woff2", ".woff": "font/woff"}
            if path.parent != (dist / "assets").resolve() or not path.exists():
                self._send(b"not found", "text/plain", 404)
            else:
                self._send(path.read_bytes(), types.get(path.suffix, "application/octet-stream"))
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
