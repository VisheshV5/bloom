"""Two hospitals' synthetic patient records (LOCAL ONLY: never ships in the FAB).

Each hospital's owner gets only their own SQLite file (python -m tasks.export_sqlite hospital-a|hospital-b)
and attaches it to their SuperNode with bloom-db. A new discharge protocol starts 2026-03-01 at both
hospitals and lowers 30-day readmission risk, so the two-hospital question has a knowable answer.
Generated from a fixed seed with random.Random.random() only, so every machine gets identical rows.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

START = date(2026, 1, 1)
END = date(2026, 6, 30)
PROTOCOL_START = date(2026, 3, 1)
DIAGNOSES = ["heart failure", "pneumonia", "COPD", "diabetes", "hip replacement", "sepsis"]
WARDS = ["cardiology", "respiratory", "general medicine", "orthopedics"]
DIAG_WARD = {"heart failure": "cardiology", "pneumonia": "respiratory", "COPD": "respiratory",
             "diabetes": "general medicine", "hip replacement": "orthopedics", "sepsis": "general medicine"}
DIAG_RISK = {"heart failure": 1.35, "pneumonia": 1.0, "COPD": 1.2, "diabetes": 0.9,
             "hip replacement": 0.6, "sepsis": 1.15}

# name, seed, admissions/day, base 30-day readmission risk, relative effect of the new protocol
SITES = {
    "hospital-a": {"name": "Hospital A", "seed": 101, "per_day": 9, "base": 0.18, "effect": 0.72},
    "hospital-b": {"name": "Hospital B", "seed": 202, "per_day": 7, "base": 0.21, "effect": 0.70},
}


def generate(site: str) -> dict[str, list[tuple]]:
    cfg = SITES[site]
    rng = random.Random(cfg["seed"])
    patients, admissions = [], []
    pid, aid = 1, 1
    day = START
    while day <= END:
        n = int(cfg["per_day"] * (0.6 + 0.8 * rng.random()) + 0.5)
        for _ in range(n):
            age = 25 + int(rng.random() * 65)
            sex = "F" if rng.random() < 0.52 else "M"
            diag = DIAGNOSES[int(rng.random() * len(DIAGNOSES))]
            patients.append((pid, age, sex))
            los = 1 + int(rng.random() * (9 if diag != "hip replacement" else 6))
            protocol = "new" if day >= PROTOCOL_START else "old"
            risk = cfg["base"] * DIAG_RISK[diag] * (1 + (age - 60) / 150)
            if protocol == "new":
                risk *= cfg["effect"]
            readmit = 1 if rng.random() < risk else 0
            admissions.append((aid, pid, day.isoformat(), (day + timedelta(days=los)).isoformat(), los,
                               DIAG_WARD[diag], diag, protocol, readmit))
            pid += 1
            aid += 1
        day += timedelta(days=1)
    return {"patients": patients, "admissions": admissions}


DDL = (
    "CREATE TABLE patients(patient_id INTEGER PRIMARY KEY, age INTEGER, sex TEXT);"
    "CREATE TABLE admissions(admission_id INTEGER PRIMARY KEY, patient_id INTEGER, admit_date TEXT, "
    "discharge_date TEXT, length_of_stay INTEGER, ward TEXT, diagnosis TEXT, protocol TEXT, readmitted_30d INTEGER);"
)
