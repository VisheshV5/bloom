"""Write the Bloom Coffee Co. database to a SQLite file for the data owner's node.

  uv run python -m tasks.export_sqlite [path]      (default: runs/coffee.sqlite)

Same seed as the benchmark, so benchmark answers match what the node's database returns.
The file is gitignored (runs/) and never part of the FAB.
"""

import sys
from pathlib import Path

from tasks.local_db import export

if __name__ == "__main__":
    out = export(Path(sys.argv[1] if len(sys.argv) > 1 else "runs/coffee.sqlite")).resolve()
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB). Attach it to the SQL node with:")
    print(f"  --node-config 'bloom-specialty=\"sql-analyst\" bloom-db=\"{out}\"'")
