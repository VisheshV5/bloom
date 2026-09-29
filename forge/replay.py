"""Replay today's REAL agent builds on the dashboard, compressed, after a session reset.

  python -m forge replay                  # session start (Generalist only), then each build
  python -m forge replay --seconds 8 --exclude currency-calculator
  python -m forge replay --final          # ...then the latest team task, messages re-timed from its trace

Every replayed event is copied from runs/events.jsonl (tagged replay=True with its original
timestamp in recorded_ts); the only derived event is the opening "generalist got a sales
question wrong", taken from a real task_result. Incomplete builds are skipped.
"""

from __future__ import annotations

import time

from forge.events import read_events

KEEP = {"forge_stage", "approval_pending", "approval_resolved", "proposal", "delivered",
        "agent_added", "node_joined", "task_result"}


def build_cycles(history: list[dict], registry) -> list[tuple[str, list[dict]]]:
    """For each active specialist, the events of its first complete build, in build order."""
    first_join = {}
    for e in history:
        if e["type"] == "agent_added" and e.get("slug") and e["slug"] not in first_join:
            first_join[e["slug"]] = e["id"]
    active = {a["slug"]: a for a in registry.active() if a["kind"] == "specialist"}
    cycles, prev_end = [], 0
    for slug in sorted((s for s in first_join if s in active), key=first_join.get):
        category = active[slug].get("category")
        end = first_join[slug]
        starts = [e["id"] for e in history if prev_end < e["id"] < end and e["type"] == "forge_stage"
                  and e.get("stage") == "architect" and e.get("category") == category]
        if not starts:
            continue
        start = starts[-1]
        events = [e for e in history if start <= e["id"] <= end + 3 and e["type"] in KEEP
                  and (e.get("slug") == slug or (e["type"] == "forge_stage" and e.get("stage") == "architect"
                                                  and e["id"] == start))
                  and not (e["type"] == "node_joined" and e["id"] > end + 3)]
        cycles.append((slug, events))
        prev_end = end
    return cycles


def replay(bus, registry, seconds_per_agent: float = 8.0, pause: float = 2.0, exclude=(), reset: bool = True,
           sleep=time.sleep, final: bool = False, final_seconds: float = 12.0) -> list[str]:
    every = read_events(bus.path)
    replayed_after = {e["id"] - 1 for e in every if e.get("replay")}
    history = [e for e in every if not e.get("replay")]
    # A replay's own "session start" is not a real reset, so replaying twice still finds every build.
    sessions = [e["id"] for e in history if e["type"] == "phase" and e.get("name") == "session start"
                and e["id"] not in replayed_after]
    if sessions:  # replay only what happened before the latest session reset
        history = [e for e in history if e["id"] < sessions[-1]]
    cycles = [(s, ev) for s, ev in build_cycles(history, registry) if s not in set(exclude)]
    if reset:
        bus.emit("phase", name="session start", replay=True)
        sleep(pause * 2)
    miss = next((e for e in history if e["type"] == "task_result" and e.get("agent") == "generalist"
                 and e.get("category") == "sql" and not e.get("correct")), None)
    if miss:
        fields = {k: v for k, v in miss.items() if k not in ("id", "ts", "type")}
        bus.emit("task_result", **fields, replay=True, recorded_ts=miss["ts"])
        bus.emit("gap_flagged", category="sql", agent="generalist", accuracy=0.0, window=1, kind="new",
                 replay=True, derived=True, recorded_ts=miss["ts"])
        sleep(pause * 1.5)
    done = []
    for slug, events in cycles:
        t0, t1 = events[0]["ts"], events[-1]["ts"]
        scale = seconds_per_agent / max(t1 - t0, 1e-6)
        last = t0
        for e in events:
            sleep(min(2.5, (e["ts"] - last) * scale))
            last = e["ts"]
            fields = {k: v for k, v in e.items() if k not in ("id", "ts", "type")}
            bus.emit(e["type"], **fields, replay=True, recorded_ts=e["ts"])
        done.append(slug)
        sleep(pause)
    if final:
        final_events = last_final(history)
        if final_events:
            replay_final(bus, final_events, final_seconds, sleep)
            done.append("final")
    bus.emit("phase", name="replay done", replay=True)
    return done


def last_final(history: list[dict]) -> list[dict]:
    """The events of the latest passing team task: its question, messages, trace, and answer."""
    finals = [e for e in history if e["type"] == "final_task" and e.get("passed")]
    if not finals:
        return []
    end = finals[-1]["id"]
    start = max((e["id"] for e in history if e["type"] == "phase" and e.get("name") == "final task" and e["id"] < end),
                default=None)
    if start is None:
        return []
    return [e for e in history if start <= e["id"] <= end]


def replay_final(bus, events: list[dict], seconds: float, sleep) -> None:
    """Messages are logged together when the run ends, so re-time them from the trace: each step's
    question goes out when the step started and its answer comes back when it ended."""
    trace = next((e for e in events if e["type"] == "trace"), {})
    steps = trace.get("steps") or []
    total = max([s.get("end_ms") or 0 for s in steps] + [1])
    at = {}
    for s in steps:
        spec = s.get("specialist")
        at[("bloom", spec)] = (s.get("start_ms") or 0) / total
        at[(spec, "bloom")] = (s.get("end_ms") or total) / total

    def emit(e):
        fields = {k: v for k, v in e.items() if k not in ("id", "ts", "type")}
        bus.emit(e["type"], **fields, replay=True, recorded_ts=e["ts"])

    head = [e for e in events if e["type"] in ("phase", "info") or (e["type"] == "message" and e.get("src") == "forge")]
    for e in head:
        emit(e)
        sleep(1.5)
    timed = sorted((e for e in events if e["type"] == "message" and e.get("src") != "forge"),
                   key=lambda e: at.get((e.get("src"), e.get("dst")), 1.0))
    clock = 0.0
    for e in timed:
        t = at.get((e.get("src"), e.get("dst")), 1.0) * seconds
        sleep(max(0.0, t - clock))
        clock = max(clock, t)
        emit(e)
    sleep(1.0)
    for e in events:
        if e["type"] in ("trace", "final_task"):
            emit(e)
