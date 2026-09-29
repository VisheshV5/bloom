"""The finale: a multi-part task that needs several specialists passing work along.

Option A ("Data detective") is implemented. The dataset plants a ~12% lift at the
Palo Alto store from 2026-04-01, so the right answer is knowable and checkable.
"""

from __future__ import annotations

from bloom.tools import dates, stats
from tasks import local_db as sql

LAUNCH = "2026-04-01"
WINDOW = 30  # business days on each side

PROMPT = (
    "Did the loyalty program launched on 2026-04-01 increase average daily revenue at the "
    "Palo Alto store? Compare the 30 business days before the launch with the first 30 "
    "business days from the launch (business days are Mon-Fri, no holidays), test whether "
    "the difference is statistically significant (Welch t-test, alpha 0.05), and write a "
    "3-sentence note for the CEO."
)

# The plan a good orchestrator should produce (used by the mock backend and shown in the README).
PLAN = [
    {"step_id": "s1", "specialist": "date-wrangler", "depends_on": [],
     "instruction": "List the 30 business days before 2026-04-01 and the first 30 business days "
                    "starting 2026-04-01. Give each window's first and last date."},
    {"step_id": "s2", "specialist": "sql-analyst", "depends_on": ["s1"],
     "instruction": "For the Palo Alto store, compute daily revenue (sum of qty*price) for every "
                    "date in both windows. Return two lists of numbers: before and after."},
    {"step_id": "s3", "specialist": "stats-analyst", "depends_on": ["s2"],
     "instruction": "Compare the before and after daily revenue lists: both means, percent change, "
                    "and a two-sided Welch t-test p-value. Is it significant at 0.05?"},
    {"step_id": "s4", "specialist": "report-writer", "depends_on": ["s1", "s2", "s3"],
     "instruction": "Write a 3-sentence note for the CEO with the key numbers and a recommendation."},
]
REQUIRED = [s["specialist"] for s in PLAN]
MISSING_CAPABILITY = {
    "capability": "report-writer",
    "category": "writing",
    "why": "The task needs a polished executive summary; no specialist writes reports.",
}


def windows() -> tuple[list[str], list[str]]:
    before_start = dates.add_business_days(LAUNCH, -WINDOW)
    before = dates.business_days_in_range(before_start, dates.add_days(LAUNCH, -1))
    after_end = dates.add_business_days(LAUNCH, WINDOW - 1)
    after = dates.business_days_in_range(LAUNCH, after_end)
    return before, after


def daily_revenue(days: list[str]) -> list[float]:
    placeholders = ",".join(f"'{d}'" for d in days)
    _, rows = sql.query(
        "SELECT date, SUM(qty*price) FROM sales JOIN stores s ON s.id = sales.store_id "
        "JOIN products p ON p.id = sales.product_id "
        f"WHERE s.city = 'Palo Alto' AND date IN ({placeholders}) GROUP BY date ORDER BY date"
    )
    return [round(r[1], 2) for r in rows]


def reference() -> dict:
    before, after = windows()
    rb, ra = daily_revenue(before), daily_revenue(after)
    t = stats.ttest_welch(ra, rb)
    mean_b, mean_a = t["mean_b"], t["mean_a"]
    return {
        "before_window": [before[0], before[-1]],
        "after_window": [after[0], after[-1]],
        "mean_before": round(mean_b, 2),
        "mean_after": round(mean_a, 2),
        "pct_change": round(100 * (mean_a - mean_b) / mean_b, 1),
        "p_value": round(t["p_value"], 4),
        "significant": t["p_value"] < 0.05,
        "before_series": rb,
        "after_series": ra,
    }


def ceo_note(ref: dict) -> str:
    p_text = "p < 0.0001" if ref["p_value"] < 0.0001 else f"p = {ref['p_value']:.4f}"
    verdict = "a statistically significant" if ref["significant"] else "no statistically significant"
    return (
        f"Palo Alto's average daily revenue rose from ${ref['mean_before']:,.2f} to "
        f"${ref['mean_after']:,.2f} ({ref['pct_change']:+.1f}%) in the 30 business days after the "
        f"loyalty program launched on 2026-04-01. A Welch t-test gives {p_text}, "
        f"which is {verdict} lift at the 5% level. Recommendation: "
        + ("roll the program out to the other three stores and keep tracking weekly revenue."
           if ref["significant"] else "keep the pilot running longer before expanding it.")
    )


def check(result_answer: str | None, ref: dict | None = None) -> bool:
    """The finale passes if the answer mentions both means (1% tolerance) and the right verdict."""
    import re

    if not result_answer:
        return False
    ref = ref or reference()
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.\d+|\d[\d,]{3,}", result_answer)]
    has = lambda target: any(abs(n - target) <= 0.01 * target for n in nums)  # noqa: E731
    says_sig = "not statistically significant" not in result_answer.lower() and "no statistically" not in result_answer.lower()
    return has(ref["mean_before"]) and has(ref["mean_after"]) and says_sig == ref["significant"]


TASK = {"id": "final-a", "category": "final", "prompt": PROMPT, "mode": "plan"}
