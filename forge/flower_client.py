"""Start Bloom AgentApp runs programmatically.

Why not `flwr run`? In flwr 1.39 the SuperLink rejects AgentApp runs without a
`user_prompt` ("A user prompt is required to start an AgentApp run"), and only
`flwr chat` sets it. So we build the same StartRunRequest that chat sends
(cli/chat/chat_app.py:start_chat_run) plus `override_config` like `flwr run` does
(cli/run/run.py:_run_with_control_api), using flwr's own helpers for the connection
(auth for SuperGrid comes from `flwr login`) and the FAB build.
Logs are then followed with `flwr log <run-id> <connection>` until the run ends.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from forge.paths import ROOT


def start_agent_run(prompt: str, overrides: dict, connection: str = "supergrid",
                    federation: str | None = None, app_dir: Path = ROOT) -> int:
    """Start one AgentApp run of the local project; return its run id."""
    from flwr.cli.build import build_fab_from_disk
    from flwr.cli.flower_config import read_superlink_connection
    from flwr.cli.utils import init_http_client_from_connection
    from flwr.common.serde import fab_to_proto, user_config_to_proto
    from flwr.proto.control_pb2 import StartRunRequest  # pylint: disable=E0611
    from flwr.supercore.fab import Fab

    conn = read_superlink_connection(connection)
    client = init_http_client_from_connection(conn)
    fab_bytes = build_fab_from_disk(app_dir)
    fab = Fab(hashlib.sha256(fab_bytes).hexdigest(), fab_bytes, {})
    req = StartRunRequest(
        fab=fab_to_proto(fab),
        override_config=user_config_to_proto(overrides),
        federation=federation or conn.federation or "",
        user_prompt=prompt,
    )
    res = client.StartRun(req)
    if not res.HasField("run_id"):
        raise RuntimeError("SuperLink did not return a run id")
    return int(res.run_id)


def follow_logs(run_id: int, connection: str = "supergrid", timeout: float = 300) -> str:
    """Stream `flwr log` until the run finishes; return all output."""
    cmd = ["uv", "run", "flwr", "log", str(run_id), connection]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=os.environ.copy())
        return proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return out + "\n[bloom] log follow timed out"


def show_logs(run_id: int, connection: str = "supergrid") -> str:
    cmd = ["uv", "run", "flwr", "log", str(run_id), connection, "--show"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120, env=os.environ.copy())
    return proc.stdout + "\n" + proc.stderr
