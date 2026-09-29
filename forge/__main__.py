"""Bloom Forge CLI.

  python -m forge demo  --backend mock [--auto-approve] [--speed 1.0] [--fresh]
  python -m forge bench --backend {mock|supergrid|nebius} [--limit N] [--join {sim|node}]
  python -m forge grow  --category sql --backend ...
  python -m forge final --backend ...
  python -m forge eval  --backend ... [--full] [--ablation] [--repeats 2] [--per-category 6]
  python -m forge describe --backend supergrid --federation @vverm/bloom-team   # discovery smoke test
  python -m forge proposals                                                      # waiting for node owners
  python -m forge activate <slug> [--node-id N] --backend supergrid --federation ...
  python -m forge registry {show|reset}
  python -m forge nodes {list|stop}
  python -m forge scan
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from forge.approval import TerminalApprover
from forge.backends import make_backend
from forge.events import EventBus
from forge.nodes import NodeManager, list_started, stop_all
from forge.paths import EVENTS, ROOT, RUNS
from forge.pipeline import Forge
from forge.registry import Registry


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", default="mock", choices=["mock", "supergrid", "nebius"])
    p.add_argument("--auto-approve", action="store_true", help="mock backend only")
    p.add_argument("--speed", type=float, default=1.0, help="mock pacing; 0 = no sleeps")
    p.add_argument("--join", default="sim", choices=["sim", "local", "node"])
    p.add_argument("--connection", default="supergrid", help="flwr SuperLink connection (supergrid | local-agent)")
    p.add_argument("--federation", default=None, help="e.g. @vverm/bloom (optional)")
    p.add_argument("--routing", default="auto", choices=["auto", "nodes", "payload", "inprocess"])
    p.add_argument("--no-build", action="store_true", help="skip `flwr build` in review")
    p.add_argument("--publish-standalone", action="store_true", help="offer to publish each specialist (asks)")
    p.add_argument("--dry-run", action="store_true", help="print SuperGrid/node commands instead of running")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--deliver-to", default=None,
                   help="deliver node-hosted proposals over the Grid to this owner's inbox node (<slug>@OWNER)")


def build_stack(args):
    bus = EventBus(echo=not args.quiet)
    registry = Registry()
    kwargs = {"speed": args.speed} if args.backend == "mock" else {
        "federation": args.federation, "dry_run": args.dry_run, "routing": args.routing,
        "connection": args.connection}
    backend = make_backend(args.backend, bus, **kwargs)
    approver = TerminalApprover(auto=args.auto_approve, backend_name=args.backend)
    if args.join != "sim" and args.backend == "mock":
        sys.exit(f"--join {args.join} needs a real backend")
    nodes = NodeManager(args.join, confirm=approver.confirm, bus=bus, federation=args.federation,
                        dry_run=args.dry_run)
    from tasks import load_benchmark

    benchmark = [t for t in load_benchmark() if t.get("split", "dev") == "dev"]  # test split is held out
    forge = Forge(backend, registry, bus, approver, nodes, benchmark,
                  run_build=not args.no_build, publish_standalone=args.publish_standalone,
                  deliver_to=getattr(args, "deliver_to", None))
    return bus, registry, backend, forge, benchmark


def fresh_start(registry: Registry, bus_path=EVENTS) -> None:
    backup = registry.reset()
    if bus_path.exists():
        bus_path.rename(backup / "events.jsonl")
    latest_eval = RUNS / "eval" / "latest.json"
    if latest_eval.exists():
        latest_eval.rename(backup / "eval-latest.json")
    print(f"Fresh start. Previous registry, events, and generated specialists moved to {backup}")


def cmd_demo(args) -> None:
    if args.backend != "mock" and args.auto_approve:
        sys.exit("--auto-approve is only allowed with the mock backend")
    if args.fresh:
        fresh_start(Registry())
    bus, registry, backend, forge, benchmark = build_stack(args)
    from evaluator.runner import Runner

    bus.emit("phase", name="start")
    bus.emit("agent_added", slug="generalist", category=None, purpose="Answers anything; no tools.",
             created_by=["human:vverm"])
    runner = Runner(backend, registry, bus, forge)
    t0 = time.time()
    r1 = runner.run(benchmark, "round 1: the team meets the benchmark")
    r2 = runner.run(benchmark, "round 2: re-test with the grown team")
    final = runner.run_final()
    active = registry.active()
    print("\n" + "=" * 72)
    print(f"Round 1: {r1}\nRound 2: {r2}")
    print(f"Team: {len(active)} agents ({sum(a['kind'] == 'specialist' for a in active)} built by Bloom): "
          + ", ".join(a["slug"] for a in active))
    print(f"Final task passed: {final['passed']}\n{final['answer']}")
    if args.eval:
        _run_eval(args, bus, registry, backend)
    bus.emit("phase", name="done")
    print(f"Took {time.time() - t0:.0f}s")


def cmd_bench(args) -> None:
    bus, registry, backend, forge, benchmark = build_stack(args)
    from evaluator.runner import Runner

    print(Runner(backend, registry, bus, forge).run(benchmark, "bench", limit=args.limit))


def cmd_grow(args) -> None:
    bus, registry, backend, forge, benchmark = build_stack(args)
    out = forge.grow({"kind": "manual", "category": args.category, "failures": []})
    print(out)


def cmd_final(args) -> None:
    bus, registry, backend, forge, benchmark = build_stack(args)
    from evaluator.runner import Runner

    print(json.dumps(Runner(backend, registry, bus, forge).run_final(), indent=2, default=str))


def _run_eval(args, bus, registry, backend) -> dict:
    from evaluator.eval import format_table, run_eval
    from tasks import load_benchmark

    tasks = [t for t in load_benchmark() if t.get("split") == "test"]
    if getattr(args, "categories", None):
        tasks = [t for t in tasks if t["category"] in args.categories.split(",")]
    per_cat = getattr(args, "per_category", None) or None
    if per_cat:
        kept, counts = [], {}
        for t in tasks:
            counts[t["category"]] = counts.get(t["category"], 0) + 1
            if counts[t["category"]] <= per_cat:
                kept.append(t)
        tasks = kept
    arms = ["generalist_tools", "specialist"]  # default: the one comparison that matters
    if getattr(args, "full", False):
        arms = ["generalist"] + arms
    if getattr(args, "ablation", False):
        arms = arms + ["generalist_tools_check"]
    report = run_eval(backend, registry, tasks, repeats=getattr(args, "repeats", 1),
                      model=getattr(args, "model", None), bus=bus, arms=arms)
    print("\n" + format_table(report))
    print("Saved runs/eval/latest.json")
    return report


def cmd_eval(args) -> None:
    bus, registry, backend, forge, benchmark = build_stack(args)
    _run_eval(args, bus, registry, backend)


def cmd_describe(args) -> None:
    bus, registry, backend, forge, benchmark = build_stack(args)
    if not hasattr(backend, "describe"):
        sys.exit("describe needs --backend supergrid")
    res = backend.describe(registry.snapshot())
    print(json.dumps({k: res.get(k) for k in ("answer", "discovery_ms", "discovered", "error")}, indent=2, default=str))


def cmd_deliver(args) -> None:
    bus, registry, backend, forge, benchmark = build_stack(args)
    if not args.deliver_to:
        sys.exit("--deliver-to OWNER is required (the part after @ in their node names, e.g. brian)")
    from forge.paths import PROPOSALS

    proposal = json.loads((PROPOSALS / f"{args.slug}.json").read_text())
    print(json.dumps(forge.deliver_proposal(proposal), indent=2, default=str))


def cmd_session(_args) -> None:
    EventBus(echo=False).emit("phase", name="session start")
    print("Dashboard reset to the Generalist (nothing else changed: agents and nodes keep running).")


def cmd_replay(args) -> None:
    from forge.replay import replay

    bus = EventBus(echo=not args.quiet)
    done = replay(bus, Registry(), seconds_per_agent=args.seconds, exclude=args.exclude or ())
    print("Replayed:", ", ".join(done))


def cmd_approve(args) -> None:
    from forge.owner import approve

    approver = TerminalApprover(auto=False)  # a node owner's approval is never automatic
    out = approve(args.slug, args.db, args.site, args.name, args.federation, approver.confirm,
                  start=not args.no_start, bus=EventBus(echo=False))
    print(json.dumps({k: v for k, v in out.items() if k != "settings"}, indent=2, default=str))


def cmd_proposals(_args) -> None:
    from forge.activation import pending

    rows = pending()
    reg = Registry()
    for r in rows:
        status = (reg.get(r["slug"]) or {}).get("status", "?")
        print(f"{r['slug']:18} {status:9} sha256 {str(r['spec_sha256'])[:16]}…  {r['path']}")
    if not rows:
        print("No proposals. Node-hosted specialists appear here after `forge grow ... --join node`.")


def cmd_activate(args) -> None:
    from forge.activation import activate

    bus, registry, backend, forge, benchmark = build_stack(args)
    from forge.activation import list_nodes

    out = activate(registry, args.slug, node_id=args.node_id, bus=bus,
                   backend=None if args.no_warm or args.backend != "supergrid" else backend, timeout=args.timeout,
                   lister=lambda: list_nodes(args.federation), owner=args.owner)
    print(json.dumps({k: v for k, v in out.items() if k != "warm_up"}, indent=2))
    if out.get("warm_up"):
        print("warm-up:", out["warm_up"].get("answer"))


def cmd_registry(args) -> None:
    registry = Registry()
    if args.action == "show":
        for a in registry.agents:
            scores = {c: f"{s['correct']}/{s['attempts']}" for c, s in a["scores"].items()}
            print(f"{a['slug']:16} {a['kind']:11} {a['status']:7} node={a['node'].get('mode')} scores={scores}")
    elif args.action == "retire":
        for slug in args.slugs:
            registry.retire(slug, "replaced for the hospital scenario")
            print(f"retired {slug}")
    elif args.action == "reset":
        if input("Reset registry to generalist-only? Current state is backed up to runs/backup/. [y/N] ").strip() in {"y", "Y"}:
            fresh_start(registry)


def cmd_nodes(args) -> None:
    if args.action == "list":
        print(json.dumps(list_started(), indent=2))
    elif args.action == "start":
        from forge.envfile import describe
        from forge.nodes import start_registered

        print(f".env: {describe()}")
        from forge.activation import list_nodes

        reg = Registry()
        ids = {(reg.get(sl) or {}).get("node", {}).get("node_id") for sl in args.slugs}
        for _ in range(24):  # SuperGrid refuses a new session while the old one still shows online
            busy = [n for n in list_nodes() if str(n.get("node-id")) in ids and n.get("status") == "online"]
            if not busy:
                break
            print(f"waiting for {len(busy)} old session(s) to go offline…")
            time.sleep(5)
        for slug in args.slugs:
            print(f"started {slug} (pid {start_registered(slug)}); logs in runs/nodes/{slug}.log")
    else:
        print("Stopped:", stop_all(args.slugs or None))


def cmd_scan(_args) -> None:
    from forge.secret_scan import scan_tree

    hits = scan_tree(ROOT)
    print("Secret scan: clean." if not hits else "Possible secrets:\n  " + "\n  ".join(hits))
    sys.exit(1 if hits else 0)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m forge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("demo"); _common(p); p.add_argument("--fresh", action="store_true")
    p.add_argument("--eval", action="store_true", help="run the held-out eval at the end")
    p = sub.add_parser("bench"); _common(p); p.add_argument("--limit", type=int)
    p = sub.add_parser("grow"); _common(p); p.add_argument("--category", required=True)
    p = sub.add_parser("final"); _common(p)
    p = sub.add_parser("eval"); _common(p)
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--per-category", type=int, default=6, help="held-out tasks per category (0 = all)")
    p.add_argument("--full", action="store_true", help="also run the plain generalist (no tools)")
    p.add_argument("--categories", default=None, help="comma separated, e.g. sql,stats")
    p.add_argument("--model", default=None, help="one model for all arms (default: generalist's)")
    p.add_argument("--ablation", action="store_true",
                   help="add a 4th arm: generalist+tools with a generic self-check")
    p = sub.add_parser("registry"); p.add_argument("action", choices=["show", "reset", "retire"])
    p.add_argument("slugs", nargs="*")
    p = sub.add_parser("nodes"); p.add_argument("action", choices=["list", "start", "stop"])
    p.add_argument("slugs", nargs="*", help="for start: registered specialists, e.g. sql-analyst stats-analyst")
    sub.add_parser("scan")
    p = sub.add_parser("describe"); _common(p)
    sub.add_parser("proposals")
    p = sub.add_parser("session"); p.add_argument("action", choices=["start"])
    p = sub.add_parser("replay"); p.add_argument("--seconds", type=float, default=8.0)
    p.add_argument("--exclude", nargs="*"); p.add_argument("--quiet", action="store_true")
    p = sub.add_parser("deliver"); _common(p); p.add_argument("slug")
    p = sub.add_parser("approve"); p.add_argument("slug"); p.add_argument("--db"); p.add_argument("--site")
    p.add_argument("--name"); p.add_argument("--federation"); p.add_argument("--no-start", action="store_true")
    p = sub.add_parser("activate"); _common(p); p.add_argument("slug")
    p.add_argument("--node-id", default=None); p.add_argument("--no-warm", action="store_true")
    p.add_argument("--owner", default=None, help="detect the owner's new online node (e.g. brianhuang08)")
    p.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    RUNS.mkdir(exist_ok=True)
    {"demo": cmd_demo, "bench": cmd_bench, "grow": cmd_grow, "final": cmd_final, "eval": cmd_eval,
     "session": cmd_session, "replay": cmd_replay,
     "describe": cmd_describe, "proposals": cmd_proposals, "activate": cmd_activate, "deliver": cmd_deliver,
     "approve": cmd_approve,
     "registry": cmd_registry, "nodes": cmd_nodes, "scan": cmd_scan}[args.cmd](args)


if __name__ == "__main__":
    main()
