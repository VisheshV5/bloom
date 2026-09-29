"""The live part of the demo, started by the dashboard's Continue button (or `python -m forge live`).

After the replay (Stats, Writing, Info), the team is asked the two-hospital question. No agent can
read patient records, so Bloom:
  1. flags the gap and shows the hospital records agent as a proposal,
  2. delivers it over the Flower Grid to Brian's inbox node (his launcher asks him y/N),
  3. waits while each hospital owner approves on their own laptop (Brian via his launcher; Vishesh's
     Hospital B starts right away if he pre-approved this exact fingerprint earlier with `forge approve`,
     otherwise he runs `forge approve` and types y), watching the Grid with
     describe runs until each hospital's node answers as an approved hospital-sql-analyst,
  4. adds each hospital's flower as its node joins, then answers the question on the live Grid, using the
     saved plan (Hospital A, Hospital B, Stats, Writing) so it takes one queued run instead of two.
The delivery run itself keeps re-discovering nodes until both hospitals are ready, so waiting for the
owners doesn't queue a new SuperGrid run for every check.
Nothing is approved here: a node only appears once its owner said y on their own machine.
"""

from __future__ import annotations

import json
import time

from forge.paths import PROPOSALS

SLUG = "hospital-sql-analyst"
SITES = {"hospital-a": "brian", "hospital-b": "vishesh"}


def site_of(d: dict) -> str | None:
    site = d.get("site")
    return str(site).strip().lower().replace(" ", "-") if site else None


def joined_sites(discovered: list[dict], slug: str = SLUG) -> dict[str, dict]:
    """site -> discovery entry, for nodes that run `slug`, hold a database and approved its spec."""
    out = {}
    for d in discovered or []:
        site = site_of(d)
        if d.get("specialist") == slug and d.get("approved") and d.get("has_db") and site in SITES:
            out.setdefault(site, d)
    return out


def run_live(bus, registry, backend, forge, runner, deliver_to: str = "brian", timeout: float = 900,
             poll: float = 10, sleep=time.sleep, start_local: bool = True, saved_plan: bool = True) -> dict:
    bus.emit("phase", name="live")
    proposal = json.loads((PROPOSALS / f"{SLUG}.json").read_text())
    spec = proposal["spec"]
    bus.emit("gap_flagged", category=spec.get("category"), agent="planner", accuracy=None, kind="capability",
             capability="hospital patient records",
             why="The question needs both hospitals' patient records, and no agent on the team can read them.")
    sleep(2)
    bus.emit("proposal", slug=SLUG, category=spec.get("category"), purpose=spec.get("purpose"),
             tools=spec.get("tools"), tests=(proposal.get("reviewer_results") or {}).get("tests"),
             spec_sha256=proposal.get("spec_sha256"))
    if start_local:  # this laptop's hospital (B) was approved by its owner beforehand: start it first
        from forge.owner import start_preapproved

        start_preapproved(SLUG, getattr(backend, "federation", None), bus=bus)

    seen: dict[str, dict] = {}

    def record(discovered: list[dict]) -> None:
        """Bloom a flower for every hospital whose node is now ready (owner said y, node online)."""
        for site, d in joined_sites(discovered).items():
            if site in seen:
                continue
            seen[site] = d
            name = str(d.get("node_name") or "")
            owner = name.split("@", 1)[1] if "@" in name else SITES[site]
            node = {"mode": "node", "node_id": str(d.get("node_id")), "name": name or f"{SLUG}@{owner}"}
            if (registry.get(SLUG) or {}).get("status") != "active":
                registry.activate(SLUG, node, approved_by=f"node-owner:{owner}")
                bus.emit("agent_added", slug=SLUG, category=spec.get("category"), purpose=spec.get("purpose"),
                         created_by=(registry.get(SLUG) or {}).get("created_by"))
            bus.emit("node_joined", slug=SLUG, node_id=node["node_id"], site=site, owner=owner, simulated=False)
            print(f"{site} joined: node {node['node_id']} ({owner})")
            sleep(1.5)

    # One Grid run delivers to Brian's inbox AND keeps watching until both hospitals are ready, instead of
    # queueing a new SuperGrid run for every check (each queued run can wait minutes before it starts).
    want = {"specialist": SLUG, "sites": sorted(SITES)}
    bus.emit("forge_stage", stage="delivering", slug=SLUG, owner=deliver_to)
    res = backend.deliver(proposal, deliver_to, await_sites=want)
    bus.emit("delivered", slug=SLUG, owner=deliver_to, ok=bool(res.get("ok")), node_id=res.get("node_id"),
             node_name=res.get("node_name"), error=res.get("error"))
    if not res.get("ok"):
        raise RuntimeError(f"delivery to {deliver_to} failed: {res.get('error')}")
    record(res.get("discovered"))

    deadline = time.monotonic() + timeout
    while len(seen) < len(SITES):  # still waiting (e.g. Brian hasn't typed y yet): watch in longer runs
        if time.monotonic() > deadline:
            raise TimeoutError(f"only {sorted(seen) or 'no'} hospital node(s) joined within {timeout:.0f}s")
        for other in SITES:
            if other not in seen:
                bus.emit("waiting_owner", slug=SLUG, site=other, owner=SITES[other])
                break
        record(backend.describe(registry.snapshot(), await_sites=want).get("discovered"))
    sleep(2)
    return runner.run_final(saved_plan=saved_plan)
