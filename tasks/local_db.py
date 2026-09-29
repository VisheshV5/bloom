"""Full-access, in-memory copies of each hospital's records for computing benchmark answers locally.

This is the benchmark author's view (unrestricted SQL). Agents never use it: they only get the
read-only, aggregate-only run_sql tool on a node that has its own hospital's file attached.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from tasks import hospital_data

DEFAULT_SITE = "hospital-a"
_conns: dict[str, sqlite3.Connection] = {}
_lock = threading.RLock()


def _fill(conn: sqlite3.Connection, site: str) -> None:
    data = hospital_data.generate(site)
    conn.executescript(hospital_data.DDL)
    conn.executemany("INSERT INTO patients VALUES (?,?,?)", data["patients"])
    conn.executemany("INSERT INTO admissions VALUES (?,?,?,?,?,?,?,?,?)", data["admissions"])
    conn.commit()


def query(sql: str, site: str = DEFAULT_SITE) -> tuple[list[str], list[tuple]]:
    with _lock:
        if site not in _conns:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            _fill(conn, site)
            _conns[site] = conn
        cur = _conns[site].execute(sql)
        return [d[0] for d in cur.description or []], cur.fetchall()


def export(path: Path, site: str = DEFAULT_SITE) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()  # regenerate: same seed, identical contents
    conn = sqlite3.connect(path)
    _fill(conn, site)
    conn.close()
    return path
