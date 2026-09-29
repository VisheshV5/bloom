"""Approve a proposal as a NODE OWNER on this machine (Vishesh = Hospital B), like Brian's launcher.

  python -m forge approve records-analyst --db runs/hospital-b.sqlite --site "Hospital B" \\
      --name records-analyst@vishesh --federation @vverm/bloom-team

Shows the spec and module, verifies the hash, asks y/N (never automatic), appends spec_sha256 to
~/.bloom/approved.json, saves this node's settings (db/site/name/approved), then registers the node
under --name, adds it to the federation, and starts it with those settings.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bloom.specs import spec_from_source, spec_hash
from forge.nodes import NodeManager, load_settings, save_settings
from forge.paths import PROPOSALS, ROOT

APPROVED = Path("~/.bloom/approved.json").expanduser()


def show(proposal: dict, out=print) -> None:
    spec = proposal["spec"]
    bar = "=" * 78
    out(f"\n{bar}\nPROPOSAL  {proposal['slug']}   spec_sha256 {proposal['spec_sha256'][:16]}…\n{bar}")
    out(f"Purpose : {spec.get('purpose')}\nTools   : {', '.join(spec.get('tools') or []) or 'none'}"
        f"\nModel   : {spec.get('model')}\nReview  : {json.dumps((proposal.get('reviewer_results') or {}).get('tests'))}")
    out(f"\nInstructions:\n  {spec.get('instructions')}\n\n--- module source ---\n{proposal['module_source']}\n{bar}")


def approve(slug: str, db: str | None, site: str | None, name: str | None, federation: str | None,
            confirm, out=print, start: bool = True, bus=None) -> dict:
    proposal = json.loads((PROPOSALS / f"{slug}.json").read_text())
    digest = spec_hash(spec_from_source(proposal["module_source"]))
    if digest != proposal.get("spec_sha256"):
        raise RuntimeError("spec_sha256 does not match the module source: refusing.")
    show(proposal, out)
    if not confirm(f"Approve {slug} to run on this machine{f' with {site} data' if site else ''}?"):
        out("Not approved. Nothing was started.")
        return {"approved": False}
    APPROVED.parent.mkdir(parents=True, exist_ok=True)
    try:
        hashes = json.loads(APPROVED.read_text() or "[]")
    except (OSError, ValueError):
        hashes = []
    if digest not in hashes:
        hashes.append(digest)
        APPROVED.write_text(json.dumps(hashes, indent=2))
    settings = {**load_settings(slug), "approved": str(APPROVED)}
    if db:
        settings["db"] = str(Path(db).expanduser().resolve())
    if site:
        settings["site"] = site
    if name:
        settings["name"] = name
    save_settings(slug, settings)
    node = None
    if start:
        # The owner just said yes to exactly this, so the node commands run without a second prompt.
        node = NodeManager("node", confirm=lambda q: True, bus=bus, federation=federation).join(slug)
    return {"approved": True, "spec_sha256": digest, "settings": settings, "node": node}


def start_preapproved(slug: str, federation: str | None, bus=None, out=print) -> dict | None:
    """Start this machine's node for `slug` without a prompt, but ONLY if the owner already approved this
    exact spec fingerprint (it is in ~/.bloom/approved.json) and saved its settings (db/site/name) earlier
    with `forge approve`. Anything new or changed still needs a fresh `forge approve` and a typed y."""
    proposal = json.loads((PROPOSALS / f"{slug}.json").read_text())
    digest = spec_hash(spec_from_source(proposal["module_source"]))
    try:
        approved = set(json.loads(APPROVED.read_text() or "[]"))
    except (OSError, ValueError):
        approved = set()
    settings = load_settings(slug)
    if digest != proposal.get("spec_sha256") or digest not in approved or not settings.get("db"):
        out(f"{slug}: not pre-approved on this machine (run `forge approve {slug}` to review it and type y).")
        return None
    out(f"{slug}: fingerprint {digest[:12]}… was already approved here; starting {settings.get('site')} node.")
    keys = ROOT / "keys"
    if (keys / slug).exists():  # SuperGrid never lets an unregistered node's key be reused: start with a fresh pair
        backup = ROOT / "runs" / "backup" / "keys" / time.strftime("%Y%m%d-%H%M%S")
        backup.mkdir(parents=True, exist_ok=True)
        for f in (keys / slug, keys / f"{slug}.pub"):
            if f.exists():
                f.rename(backup / f.name)
    return NodeManager("node", confirm=lambda q: True, bus=bus, federation=federation).join(slug)
