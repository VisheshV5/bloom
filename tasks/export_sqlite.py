"""Write one hospital's records to a SQLite file for that hospital's node.

  uv run python -m tasks.export_sqlite hospital-a [path]   (default: runs/hospital-a.sqlite)
  uv run python -m tasks.export_sqlite hospital-b [path]

Same seed everywhere, so benchmark answers match what each node's database returns.
The file is gitignored (runs/) and never part of the FAB. Each owner only needs their own site.
"""

import hashlib
import sys
from pathlib import Path

from tasks.hospital_data import SITES
from tasks.local_db import export

if __name__ == "__main__":
    site = sys.argv[1] if len(sys.argv) > 1 else "hospital-a"
    if site not in SITES:
        sys.exit(f"site must be one of {sorted(SITES)}")
    out = export(Path(sys.argv[2] if len(sys.argv) > 2 else f"runs/{site}.sqlite").expanduser(), site).resolve()
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB, sha256 {digest[:12]}…) for {SITES[site]['name']}.")
    print(f"  --node-config '... bloom-db=\"{out}\" bloom-site=\"{SITES[site]['name']}\"'")
