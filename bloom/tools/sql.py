"""run_sql: read-only, aggregate-only SQL over a database the NODE OWNER attaches.

The data never ships in the FAB. A SuperNode's owner attaches their SQLite file with
  --node-config 'bloom-specialty="sql-analyst" bloom-db="/abs/path/coffee.sqlite"'
and only then does run_sql exist on that node. Without a database the tool is absent from
the tool list, so the coordinator (and any node without the file) genuinely cannot answer.
Queries must be one SELECT that aggregates (GROUP BY or an aggregate function) and never
`SELECT *`, so row-level records can't be pulled out; results are capped at 200 rows.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from urllib.parse import quote

SCHEMA_DESCRIPTION = (
    "SQLite tables: stores(id, name, city, opened), "
    "products(id, name, category, price), "
    "sales(id, store_id, product_id, date TEXT 'YYYY-MM-DD', qty). "
    "Revenue = sales.qty * products.price. Data covers 2026-01-01 to 2026-06-30."
)
MAX_ROWS = 200

_db_path: str | None = None
_lock = threading.RLock()
_AGGREGATE = re.compile(r"\b(sum|count|avg|min|max|total|group_concat)\s*\(", re.I)
_GROUP_BY = re.compile(r"\bgroup\s+by\b", re.I)
_STAR = [re.compile(r"\bselect\s+(distinct\s+)?(\w+\.)?\*\s*(,|\bfrom\b)", re.I),
         re.compile(r",\s*(\w+\.)?\*\s*(,|\bfrom\b)", re.I)]
_READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                 getattr(sqlite3, "SQLITE_RECURSIVE", 33)}


def configure(path: str | None) -> bool:
    """Attach the node owner's database (absolute path). Returns whether it's usable."""
    global _db_path
    with _lock:
        _db_path = str(Path(path).expanduser()) if path and Path(path).expanduser().is_file() else None
        return _db_path is not None


def available() -> bool:
    return _db_path is not None


def validate(sql: str) -> str:
    text = sql.strip().rstrip(";").strip()
    if ";" in text:
        raise ValueError("Only one statement is allowed.")
    if not text.lower().startswith(("select", "with")):
        raise ValueError("Only SELECT queries are allowed.")
    if any(p.search(text) for p in _STAR):
        raise ValueError("SELECT * is not allowed; select aggregated columns.")
    if not (_AGGREGATE.search(text) or _GROUP_BY.search(text)):
        raise ValueError("Queries must aggregate (GROUP BY or SUM/COUNT/AVG/MIN/MAX); row-level data is not returned.")
    return text


def _authorizer(action, *_args):
    return sqlite3.SQLITE_OK if action in _READ_ACTIONS else sqlite3.SQLITE_DENY


def query(sql: str) -> tuple[list[str], list[tuple], bool]:
    """Run one validated query read-only. Returns (columns, rows, truncated)."""
    if not available():
        raise RuntimeError("No database is attached to this machine.")
    text = validate(sql)
    with _lock:
        conn = sqlite3.connect(f"file:{quote(_db_path)}?mode=ro", uri=True, check_same_thread=False)
        try:
            conn.set_authorizer(_authorizer)
            cur = conn.execute(text)
            columns = [d[0] for d in cur.description or []]
            rows = cur.fetchmany(MAX_ROWS + 1)
        finally:
            conn.close()
    return columns, rows[:MAX_ROWS], len(rows) > MAX_ROWS


def run_sql(query_text: str) -> dict:
    """Tool entry point."""
    columns, rows, truncated = query(query_text)
    return {"columns": columns, "rows": [list(r) for r in rows], "row_count": len(rows), "truncated": truncated}
