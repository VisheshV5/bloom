"""Bloom Coffee Co.: a small deterministic sales dataset (LOCAL ONLY: never ships in the FAB).

The data owner gets it as a SQLite file (python -m tasks.export_sqlite) and attaches it to
their SuperNode with --node-config 'bloom-db="/abs/path/coffee.sqlite"'.

Generated from a fixed seed at import time using only `random.Random.random()`
so every machine (laptop, SuperLink, SuperNode) sees identical rows.
The Palo Alto store gets a ~12% lift from 2026-04-01 (the "loyalty program").
"""

from __future__ import annotations

import random
from datetime import date, timedelta

SEED = 42
START = date(2026, 1, 1)
END = date(2026, 6, 30)
LOYALTY_LAUNCH = date(2026, 4, 1)
LOYALTY_STORE_ID = 2
LOYALTY_LIFT = 1.12

# (id, name, city, opened)
STORES = [
    (1, "Downtown", "San Francisco", "2024-03-01"),
    (2, "University Ave", "Palo Alto", "2024-09-15"),
    (3, "Castro St", "Mountain View", "2025-02-01"),
    (4, "Santana Row", "San Jose", "2025-06-10"),
]

# (id, name, category, price in USD)
PRODUCTS = [
    (1, "Espresso", "coffee", 3.25),
    (2, "Latte", "coffee", 5.10),
    (3, "Cappuccino", "coffee", 4.85),
    (4, "Cold Brew", "coffee", 4.95),
    (5, "Matcha Latte", "tea", 5.60),
    (6, "Chai", "tea", 4.40),
    (7, "Croissant", "pastry", 3.75),
    (8, "Blueberry Muffin", "pastry", 3.50),
    (9, "Almond Scone", "pastry", 3.95),
    (10, "Beans 12oz", "retail", 17.00),
]

_STORE_BASE = {1: 1.30, 2: 1.00, 3: 0.85, 4: 0.95}
_PRODUCT_BASE = {1: 22, 2: 30, 3: 18, 4: 16, 5: 10, 6: 9, 7: 20, 8: 12, 9: 8, 10: 3}
_WEEKDAY_FACTOR = [1.0, 1.0, 1.05, 1.05, 1.15, 0.8, 0.7]  # Mon..Sun


def _generate() -> list[tuple[int, int, int, str, int]]:
    rng = random.Random(SEED)
    rows = []
    row_id = 1
    day = START
    while day <= END:
        # Mild seasonality: +10% by June.
        season = 1.0 + 0.10 * (day - START).days / (END - START).days
        for store_id, _, _, _ in STORES:
            lift = LOYALTY_LIFT if (store_id == LOYALTY_STORE_ID and day >= LOYALTY_LAUNCH) else 1.0
            for product_id, *_ in PRODUCTS:
                base = (
                    _STORE_BASE[store_id]
                    * _PRODUCT_BASE[product_id]
                    * _WEEKDAY_FACTOR[day.weekday()]
                    * season
                    * lift
                )
                qty = int(base * (0.7 + 0.6 * rng.random()) + 0.5)
                rows.append((row_id, store_id, product_id, day.isoformat(), qty))
                row_id += 1
        day += timedelta(days=1)
    return rows


# (id, store_id, product_id, date, qty)
SALES = _generate()

from bloom.tools.sql import SCHEMA_DESCRIPTION  # noqa: E402,F401 - one source of truth
