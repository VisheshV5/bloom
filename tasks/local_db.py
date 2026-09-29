"""Full-access, in-memory copy of the dataset for computing benchmark answers locally.

This is the benchmark author's view (unrestricted SQL). Agents never use it: they only get
the read-only, aggregate-only run_sql tool on a node that has the database attached.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from tasks import coffee_data

_conn: sqlite3.Connection | None = None
_lock = threading.RLock()

DDL = (
    "CREATE TABLE stores(id INTEGER PRIMARY KEY, name TEXT, city TEXT, opened TEXT);"
    "CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL);"
    "CREATE TABLE sales(id INTEGER PRIMARY KEY, store_id INTEGER, product_id INTEGER, date TEXT, qty INTEGER);"
)


def _fill(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.executemany("INSERT INTO stores VALUES (?,?,?,?)", coffee_data.STORES)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?)", coffee_data.PRODUCTS)
    conn.executemany("INSERT INTO sales VALUES (?,?,?,?,?)", coffee_data.SALES)
    conn.commit()


def query(sql: str) -> tuple[list[str], list[tuple]]:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(":memory:", check_same_thread=False)
            _fill(_conn)
        cur = _conn.execute(sql)
        return [d[0] for d in cur.description or []], cur.fetchall()


def export(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()  # regenerate: same seed, identical contents
    conn = sqlite3.connect(path)
    _fill(conn)
    conn.close()
    return path
