"""Bring a proposed specialist online once its node owner has approved and started the node.

  python -m forge proposals                       # what's waiting for a node owner
  python -m forge activate sql-analyst            # wait for sql-analyst@<owner> to come online
  python -m forge activate sql-analyst --node-id 123 --federation @vverm/bloom-team

Matching: `flwr supernode list supergrid --format json` gives node-id / owner-name / status; if a
name is present we match "<slug>@<owner>", otherwise pass --node-id (Brian sends it back after
registering). When the node is online, the registry entry becomes active with
approved_by "node-owner:<owner>", and one throwaway describe run warms the node (FAB + deps).
"""

from __future__ import annotations

import json
import subprocess
import time

from forge.paths import PROPOSALS, ROOT

FLWR = ["uvx", "--from", "flwr==1.39.0", "flwr"]


def list_nodes(federation: str | None = None) -> list[dict]:
    """Nodes with status. `supernode list` only shows nodes YOU own; a federation lists every
    member's nodes (e.g. the data owner's), so prefer it when we know the federation."""
    if federation:
        cmd = [*FLWR, "federation", "list", "supergrid", "--federation", federation, "--format", "json"]
    else:
        cmd = [*FLWR, "supernode", "list", "supergrid", "--format", "json"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
    text = proc.stdout[proc.stdout.find("{"):] if "{" in proc.stdout else "{}"
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if federation:
        return [{"node-id": n.get("node_id"), "owner-name": n.get("owner"), "status": n.get("status")}
                for n in (data.get("federation") or {}).get("nodes", [])]
    return list(data.get("nodes", []))


def _node_id(n: dict) -> str:
    return str(n.get("node-id", n.get("node_id", n.get("id", ""))))


def find_node(slug: str, node_id: str | None, nodes: list[dict], owner: str | None = None,
              taken: set[str] = frozenset()) -> dict | None:
    if owner and not node_id:  # a new online node of that owner that no agent uses yet
        fresh = [n for n in nodes if (n.get("owner-name") == owner and _node_id(n) not in taken
                                      and str(n.get("status", "")).lower() == "online")]
        return fresh[0] if fresh else None
    for n in nodes:
        if node_id and _node_id(n) == str(node_id):
            return n
        if not node_id and str(n.get("name", "")).split("@")[0] == slug:
            return n
    return None


def activate(registry, slug: str, node_id: str | None = None, bus=None, backend=None,
             timeout: float = 600, poll: float = 10, lister=list_nodes, sleep=time.sleep,
             owner: str | None = None) -> dict:
    entry = registry.get(slug)
    if entry is None:
        raise ValueError(f"{slug} is not in the registry")
    deadline = time.monotonic() + timeout
    node = None
    while time.monotonic() < deadline:
        taken = {str((a.get("node") or {}).get("node_id")) for a in registry.agents if a["slug"] != slug}
        node = find_node(slug, node_id, lister(), owner=owner, taken=taken)
        if node and str(node.get("status", "")).lower() == "online":
            break
        state = node.get("status") if node else "not registered yet"
        print(f"waiting for {slug}'s node ({state})…")
        sleep(poll)
    else:
        raise TimeoutError(f"{slug}'s node did not come online within {timeout:.0f}s")
    owner = node.get("owner-name") or node.get("owner") or "unknown"
    info = {"mode": "node", "node_id": _node_id(node), "name": node.get("name") or f"{slug}@{owner}"}
    registry.activate(slug, info, approved_by=f"node-owner:{owner}")
    if bus:
        bus.emit("agent_added", slug=slug, category=entry.get("category"), purpose=entry.get("purpose"),
                 created_by=entry.get("created_by"))
        bus.emit("node_joined", slug=slug, node_id=info["node_id"], simulated=False, owner=owner)
    warm = None
    if backend is not None and hasattr(backend, "describe"):
        warm = backend.describe(registry.snapshot())  # first run on a fresh node syncs deps: do it now
    return {"slug": slug, "node": info, "approved_by": f"node-owner:{owner}", "warm_up": warm}


def pending() -> list[dict]:
    out = []
    for path in sorted(PROPOSALS.glob("*.json")):
        try:
            p = json.loads(path.read_text())
        except ValueError:
            continue
        out.append({"slug": p.get("slug"), "spec_sha256": p.get("spec_sha256"), "path": str(path.relative_to(ROOT)),
                    "created_at": p.get("created_at")})
    return out
