"""Optional: publish a specialist as its own Flower Hub app `@vverm/bloom-test-<slug>`.

The standalone app is a copy of the bloom package whose AgentApp always runs one
specialist on the chat prompt. Publishing ALWAYS asks first; mock mode only simulates.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from forge.paths import ROOT
from forge.secret_scan import scan_tree

OUT_ROOT = ROOT.parent / "bloom-agents"  # outside the repo: publish uploads the whole project dir

STANDALONE_APP = '''"""Standalone Bloom specialist: {slug}."""

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

from bloom import llm
from bloom.protocol import Step
from bloom.specialist import resolve_spec, run_spec

SLUG = "{slug}"
app = AgentApp()


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    spec, post, _ = resolve_spec(SLUG, None)
    result = run_spec(spec, Step("chat", "s1", SLUG, agent.prompt), postprocess=post)
    llm.emit_text(agent, result.output or f"Error: {{result.error}}")
'''


def build_standalone(slug: str, purpose: str) -> Path:
    name = f"bloom-test-{slug}"
    out = OUT_ROOT / name
    if out.exists():
        raise FileExistsError(f"{out} already exists; move it away first (not deleting it automatically).")
    out.mkdir(parents=True)
    shutil.copytree(ROOT / "bloom", out / "bloom", ignore=shutil.ignore_patterns("__pycache__"))
    (out / "bloom" / "standalone.py").write_text(STANDALONE_APP.format(slug=slug))
    shutil.copy2(ROOT / "LICENSE", out / "LICENSE")
    shutil.copy2(ROOT / ".gitignore", out / ".gitignore")
    pyproject = (ROOT / "pyproject.toml").read_text()
    pyproject = pyproject.replace('name = "bloom"', f'name = "{name}"', 1)
    pyproject = pyproject.replace('display-name = "Bloom"', f'display-name = "Bloom {slug}"', 1)
    pyproject = pyproject.replace('agentapp = "bloom.agent_app:app"', 'agentapp = "bloom.standalone:app"', 1)
    pyproject = pyproject.split("[tool.pytest")[0].replace('[dependency-groups]\ndev = ["pytest>=8"]\n\n', "")
    (out / "pyproject.toml").write_text(pyproject)
    (out / "README.md").write_text(
        f"---\ntags: [agentapp]\ndataset: []\nframework: []\n---\n\n# {name}\n\n{purpose}\n\n"
        "Created by Bloom's Forge (Architect, Builder, Reviewer agents) and approved by a human.\n"
    )
    return out


def publish(slug: str, purpose: str, confirm, simulate: bool, bus=None) -> str | None:
    name = f"bloom-test-{slug}"
    if simulate:
        if bus:
            bus.emit("published", slug=slug, hub=f"@vverm/{name}", simulated=True)
        return f"@vverm/{name} (simulated)"
    out = build_standalone(slug, purpose)
    build = subprocess.run(["uv", "run", "--project", str(ROOT), "flwr", "build", "--app", str(out)],
                           cwd=out, capture_output=True, text=True, timeout=180)
    for fab in out.glob("*.fab"):
        fab.unlink()
    if build.returncode != 0:
        raise RuntimeError(f"standalone build failed: {build.stderr[-800:]}")
    hits = scan_tree(out)
    if hits:
        raise RuntimeError("Refusing to publish, possible secrets:\n  " + "\n  ".join(hits))
    if not confirm(f"Publish @vverm/{name} to Flower Hub (PUBLIC, immediate) from {out}?"):
        return None
    proc = subprocess.run(["uv", "run", "--project", str(ROOT), "flwr", "app", "publish", str(out)],
                          cwd=out, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"publish failed: {proc.stderr[-800:]}")
    if bus:
        bus.emit("published", slug=slug, hub=f"@vverm/{name}", simulated=False)
    return f"@vverm/{name}"
