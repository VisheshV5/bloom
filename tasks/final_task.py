"""The finale: a question that needs TWO hospitals' private records, answered with aggregates only.

Hospital A's records live only on Brian's node, Hospital B's only on Vishesh's. Each hospital's
records-analyst returns counts and rates; a stats specialist pools them; a writer explains it.
The reference answer below is computed locally from the same seeded data, so the finale is checkable.
"""

from __future__ import annotations

import math
import re

from tasks.hospital_data import PROTOCOL_START, SITES
from tasks.local_db import query

PROMPT = (
    "Did the new discharge protocol (used for admissions from 2026-03-01) reduce 30-day readmissions? "
    "Use BOTH Hospital A's and Hospital B's records: get each hospital's number of admissions and "
    "readmissions under the old and new protocol (aggregates only; patient-level data never leaves a "
    "hospital), then compute the pooled readmission rate before and after, the change in percentage "
    "points, and a two-sided two-proportion z-test (alpha 0.05). Write a 3-sentence note for the "
    "hospitals' joint quality committee."
)

PLAN = [
    {"step_id": "s1", "specialist": "records-analyst@hospital-a", "depends_on": [],
     "instruction": "At Hospital A, count admissions and 30-day readmissions under the old and the new discharge protocol."},
    {"step_id": "s2", "specialist": "records-analyst@hospital-b", "depends_on": [],
     "instruction": "At Hospital B, count admissions and 30-day readmissions under the old and the new discharge protocol."},
    {"step_id": "s3", "specialist": "stats-analyst", "depends_on": ["s1", "s2"],
     "instruction": "Pool both hospitals' counts: readmission rate old vs new, change in percentage points, "
                    "and a two-sided two-proportion z-test p-value."},
    {"step_id": "s4", "specialist": "writing-editor", "depends_on": ["s1", "s2", "s3"],
     "instruction": "Write a 3-sentence note for the joint quality committee with the key numbers and a recommendation."},
]
REQUIRED = [s["specialist"] for s in PLAN]
MISSING_CAPABILITY = {"capability": "report-writer", "category": "writing",
                      "why": "The task needs a polished committee note; no specialist writes reports."}


def site_counts(site: str) -> dict:
    rows = {proto: (n, r) for proto, n, r in query(
        "SELECT protocol, COUNT(*), SUM(readmitted_30d) FROM admissions GROUP BY protocol", site)[1]}
    return {"old_n": rows["old"][0], "old_readmits": rows["old"][1], "new_n": rows["new"][0], "new_readmits": rows["new"][1]}


def two_proportion_z(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    p1, p2, pool = x1 / n1, x2 / n2, (x1 + x2) / (n1 + n2)
    z = (p1 - p2) / math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    return z, math.erfc(abs(z) / math.sqrt(2))


def reference() -> dict:
    per = {SITES[s]["name"]: site_counts(s) for s in SITES}
    old_n = sum(c["old_n"] for c in per.values())
    old_r = sum(c["old_readmits"] for c in per.values())
    new_n = sum(c["new_n"] for c in per.values())
    new_r = sum(c["new_readmits"] for c in per.values())
    z, p = two_proportion_z(old_r, old_n, new_r, new_n)
    return {
        "per_hospital": per,
        "protocol_start": PROTOCOL_START.isoformat(),
        "rate_old": round(100 * old_r / old_n, 2),
        "rate_new": round(100 * new_r / new_n, 2),
        "change_pts": round(100 * (new_r / new_n - old_r / old_n), 2),
        "z": round(z, 3),
        "p_value": p,
        "significant": p < 0.05,
    }


def committee_note(ref: dict) -> str:
    p_text = "p < 0.001" if ref["p_value"] < 0.001 else f"p = {ref['p_value']:.3f}"
    verdict = "a statistically significant" if ref["significant"] else "no statistically significant"
    return (
        f"Across both hospitals, the 30-day readmission rate fell from {ref['rate_old']:.2f}% under the old discharge "
        f"protocol to {ref['rate_new']:.2f}% under the new one ({ref['change_pts']:+.2f} percentage points). "
        f"A two-proportion z-test gives z = {ref['z']:.2f}, {p_text}, {verdict} reduction at the 5% level. "
        "Recommendation: keep the new protocol at both hospitals and review readmissions by ward each month."
    )


def check(result_answer: str | None, ref: dict | None = None) -> bool:
    """Passes if the answer states both pooled rates (±0.3 points) and the right significance verdict."""
    if not result_answer:
        return False
    ref = ref or reference()
    nums = [float(x) for x in re.findall(r"\d+\.\d+", result_answer)]
    has = lambda target: any(abs(n - target) <= 0.3 for n in nums)  # noqa: E731
    text = result_answer.lower()
    says_sig = not ("not statistically significant" in text or "no statistically" in text)
    return has(ref["rate_old"]) and has(ref["rate_new"]) and says_sig == ref["significant"]


TASK = {"id": "final-hospitals", "category": "final", "prompt": PROMPT, "mode": "plan"}
