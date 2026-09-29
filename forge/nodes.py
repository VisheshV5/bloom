"""SuperNode lifecycle: how a new specialist joins the federation.

Modes:
  sim   - simulated join (mock demo); no commands run.
  local - start a real `flower-supernode --insecure` against a LOCAL SuperLink (127.0.0.1:9092).
  node - real: keygen -> `flwr supernode register --name <slug>` -> (optional)
         `flwr federation add-supernode <id> <federation>` -> start `flower-supernode`.
Every real command is printed and needs an explicit y. Private keys stay in keys/ (gitignored)
and are never printed. Model credentials are inherited from the environment, never written.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from forge.envfile import node_env
from forge.paths import KEYS, ROOT, RUNS

SUPERLINK_FLEET = "fleet-supergrid.flower.ai:443"
LOCAL_FLEET = "127.0.0.1:9092"
FLWR = ["uvx", "--from", "flwr==1.39.0", "flwr"]
PIDS = RUNS / "nodes" / "pids.json"
BASE_PORT = 9110


def node_config(slug: str) -> str:
    """--node-config for a node this laptop hosts.

    bloom-specialty always; bloom-model if BLOOM_NODE_MODEL is set; bloom-db (the owner's SQLite
    file, BLOOM_NODE_DB or runs/coffee.sqlite) ONLY for specialists that use run_sql, so the data
    sits on that one node; bloom-approved if BLOOM_APPROVED points at an approved-hashes file.
    """
    from bloom.specialists import load_specialist

    env = node_env()
    parts = [f'bloom-specialty="{slug}"']
    model = env.get("BLOOM_NODE_MODEL", "").strip()
    if model:
        parts.append(f'bloom-model="{model}"')
    mod = load_specialist(slug)
    if mod is not None and "run_sql" in getattr(mod, "TOOLS", []):
        db = Path(env.get("BLOOM_NODE_DB") or RUNS / "coffee.sqlite").expanduser().resolve()
        if db.exists():
            parts.append(f'bloom-db="{db}"')
    approved = env.get("BLOOM_APPROVED", "").strip()
    if approved:
        parts.append(f'bloom-approved="{Path(approved).expanduser()}"')
    return " ".join(parts)


def per_node_env(slug: str) -> dict:
    """Node env with its own FLWR_HOME: nodes sharing one home collide when they install the same
    run's environment at the same time ("Unable to locate site-packages in runtime environment")."""
    home = RUNS / "nodes" / "home" / slug
    home.mkdir(parents=True, exist_ok=True)
    return {**node_env(), "FLWR_HOME": str(home)}


def start_registered(slug: str) -> int:
    """Start the SuperNode for an already-registered specialist (keys/<slug>) against SuperGrid."""
    nm = NodeManager("node")
    cmd = nm._start(slug, len(_load_pids()))
    log = RUNS / "nodes" / f"{slug}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                env=per_node_env(slug), start_new_session=True)
    pids = _load_pids()
    pids[slug] = proc.pid
    _save_pids(pids)
    return proc.pid


_RESERVED: set[int] = set()


def free_port(start: int) -> int:
    """First port >= start that nothing is listening on and that we haven't already handed out
    (nodes started back to back would otherwise race for the same port before either binds)."""
    import socket

    for port in range(start, start + 200):
        if port in _RESERVED:
            continue
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        _RESERVED.add(port)
        return port
    raise RuntimeError("no free port found")


def sim_node_id(slug: str) -> str:
    return str(int(hashlib.sha256(slug.encode()).hexdigest()[:13], 16))


class NodeManager:
    def __init__(self, mode: str = "sim", confirm=None, bus=None, federation: str | None = None,
                 dry_run: bool = False):
        if mode not in {"sim", "node", "local"}:
            raise ValueError("join mode must be 'sim', 'local', or 'node'")
        self.mode = mode
        self.confirm = confirm or (lambda q: False)
        self.bus = bus
        self.federation = federation
        self.dry_run = dry_run

    # ── planning ───────────────────────────────────────────────────────────
    def planned_commands(self, slug: str) -> list[str]:
        if self.mode == "sim":
            return [f"(simulated) start SuperNode '{slug}' and add it to the federation"]
        if self.mode == "local":
            return [" ".join(self._start_local(slug, len(_load_pids()))) + "   # local SuperLink"]
        cmds = [" ".join(self._keygen(slug)), " ".join(self._register(slug))]
        if self.federation:
            cmds.append(" ".join(self._add(slug, "<node-id>")))
        cmds.append(" ".join(self._start(slug, 0)) + "   # background, logs in runs/nodes/")
        return cmds

    def _keygen(self, slug):
        return ["ssh-keygen", "-t", "ecdsa", "-b", "384", "-N", "", "-f", f"keys/{slug}"]

    def _register(self, slug):
        return [*FLWR, "supernode", "register", f"keys/{slug}.pub", "supergrid", "--name", slug, "--format", "json"]

    def _add(self, slug, node_id):
        return [*FLWR, "federation", "add-supernode", str(node_id), self.federation, "supergrid"]

    def _start(self, slug, index):
        return ["uv", "run", "flower-supernode", f"--superlink={SUPERLINK_FLEET}",
                f"--auth-supernode-private-key=keys/{slug}", "--allow-runtime-dependency-installation",
                "--node-config", node_config(slug), "--port", str(free_port(BASE_PORT + 2 * index)),
                "--health-server-address", f"127.0.0.1:{free_port(BASE_PORT + 100 + 2 * index)}"]

    def _start_local(self, slug, index):
        port = free_port(BASE_PORT + 2 * index)
        health = free_port(port + 1)
        return ["uv", "run", "flower-supernode", "--insecure", "--superlink", LOCAL_FLEET,
                "--node-config", node_config(slug), "--port", str(port),
                "--health-server-address", f"127.0.0.1:{health}"]

    def _join_local(self, slug: str) -> dict:
        cmd = self._start_local(slug, len(_load_pids()))
        log = RUNS / "nodes" / f"{slug}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        print("  $ " + " ".join(cmd))
        with log.open("w") as fh:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    env=per_node_env(slug), start_new_session=True)
        pids = _load_pids()
        pids[slug] = proc.pid
        _save_pids(pids)
        node_id = None
        for _ in range(60):
            m = re.search(r"SuperNode ID: (\d+)", log.read_text(errors="ignore"))
            if m:
                node_id = m.group(1)
                break
            time.sleep(0.5)
        node = {"mode": "local", "node_id": node_id, "name": slug}
        if self.bus:
            self.bus.emit("node_joined", slug=slug, node_id=node_id, simulated=False)
        return node

    # ── execution ──────────────────────────────────────────────────────────
    def _run(self, cmd: list[str], question: str) -> subprocess.CompletedProcess | None:
        if self.dry_run:
            print("DRY RUN:", " ".join(cmd))
            return None
        if not self.confirm(f"{question}\n  $ {' '.join(cmd)}\nRun it?"):
            raise PermissionError(f"Not approved: {' '.join(cmd)}")
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)

    def join(self, slug: str) -> dict:
        if self.mode == "sim":
            node = {"mode": "sim", "node_id": sim_node_id(slug), "name": slug}
            if self.bus:
                self.bus.emit("node_joined", slug=slug, node_id=node["node_id"], simulated=True)
            return node

        if self.mode == "local":
            return self._join_local(slug)
        KEYS.mkdir(exist_ok=True)
        if not (KEYS / slug).exists():
            self._run(self._keygen(slug), f"Create a SuperNode key pair for {slug} in keys/ (gitignored)")
        res = self._run(self._register(slug), f"Register SuperNode '{slug}' with SuperGrid")
        node_id = None
        if res is not None:
            if res.returncode != 0:
                raise RuntimeError(f"register failed: {res.stderr[-500:] or res.stdout[-500:]}")
            node_id = _parse_node_id(res.stdout)
        if self.federation and node_id:
            res = self._run(self._add(slug, node_id), f"Add node {node_id} to {self.federation}")
            if res is not None and res.returncode != 0:
                raise RuntimeError(f"add-supernode failed: {res.stderr[-500:]}")
        index = len(_load_pids())
        cmd = self._start(slug, index)
        if not self.dry_run:
            if not self.confirm(f"Start SuperNode '{slug}' in the background\n  $ {' '.join(cmd)}\nRun it?"):
                raise PermissionError("Not approved: start SuperNode")
            log = (RUNS / "nodes" / f"{slug}.log")
            log.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log.open("a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    env=per_node_env(slug), start_new_session=True)
            pids = _load_pids()
            pids[slug] = proc.pid
            _save_pids(pids)
        node = {"mode": "node", "node_id": node_id, "name": slug}
        if self.bus:
            self.bus.emit("node_joined", slug=slug, node_id=node_id, simulated=False)
        return node


def _parse_node_id(stdout: str) -> str | None:
    try:
        data = json.loads(stdout[stdout.find("{"):])
        for key in ("node_id", "node-id", "id"):
            if key in data:
                return str(data[key])
    except ValueError:
        pass
    m = re.search(r"(?:node[ _-]?id|ID)[^0-9]*(\d{5,})", stdout, re.I)
    return m.group(1) if m else None


def _load_pids() -> dict:
    try:
        return json.loads(PIDS.read_text())
    except (OSError, ValueError):
        return {}


def _save_pids(pids: dict) -> None:
    PIDS.parent.mkdir(parents=True, exist_ok=True)
    PIDS.write_text(json.dumps(pids, indent=2))


def list_started() -> dict:
    return _load_pids()


def stop_all(slugs: list[str] | None = None) -> list[str]:
    """Stop Forge-started SuperNodes (all, or just `slugs`). Wait ~30s before restarting the same
    node, or SuperGrid may refuse the new session ("Failed to activate SuperNode")."""
    stopped, pids = [], _load_pids()
    for slug, pid in list(pids.items()):
        if slugs and slug not in slugs:
            continue
        try:
            os.killpg(pid, signal.SIGTERM)
            stopped.append(slug)
        except (ProcessLookupError, PermissionError):
            pass
        pids.pop(slug, None)
    _save_pids(pids)
    return stopped
