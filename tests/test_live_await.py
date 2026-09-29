"""The live demo waits for hospital owners inside one Grid run, and only counts approved nodes with data."""

import time

from bloom import orchestrator
from forge.live import joined_sites


def cap(site, approved=True, has_db=True, specialist="hospital-sql-analyst", node_id="1"):
    return {"specialist": specialist, "site": site, "approved": approved, "has_db": has_db, "node_id": node_id}


def test_ready_sites_needs_approval_and_database():
    found = [cap("Hospital A"), cap("Hospital B", approved=False), cap("hospital-b", has_db=False),
             cap("Hospital C", specialist="stats-analyst")]
    assert orchestrator.ready_sites(found, "hospital-sql-analyst") == {"hospital-a"}
    assert set(joined_sites(found)) == {"hospital-a"}


def test_await_sites_rediscovers_until_both_ready(monkeypatch):
    rounds = [[cap("Hospital A")], [cap("Hospital A"), cap("Hospital B", node_id="2")]]
    monkeypatch.setattr(orchestrator, "AWAIT_POLL_S", 0)
    monkeypatch.setattr(orchestrator, "discover", lambda grid, nodes: rounds.pop(0))

    class Grid:
        def nodes(self):
            return [{"id": 1}, {"id": 2}]

    want = {"specialist": "hospital-sql-analyst", "sites": ["hospital-a", "hospital-b"]}
    out = orchestrator.await_sites(Grid(), want, time.monotonic() + 5, [])
    assert orchestrator.ready_sites(out, "hospital-sql-analyst") == {"hospital-a", "hospital-b"}
    assert rounds == []


def test_await_sites_stops_at_deadline(monkeypatch):
    monkeypatch.setattr(orchestrator, "AWAIT_POLL_S", 0)
    monkeypatch.setattr(orchestrator, "discover", lambda grid, nodes: [cap("Hospital A")])

    class Grid:
        def nodes(self):
            return [{"id": 1}]

    out = orchestrator.await_sites(Grid(), {"specialist": "hospital-sql-analyst", "sites": ["hospital-a", "hospital-b"]},
                                   time.monotonic() + 0.05, [])
    assert orchestrator.ready_sites(out, "hospital-sql-analyst") == {"hospital-a"}
