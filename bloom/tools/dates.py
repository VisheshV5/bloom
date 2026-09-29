"""Calendar and business-day arithmetic (Mon-Fri, no holidays)."""

from __future__ import annotations

from datetime import date, timedelta

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _d(value: str) -> date:
    return date.fromisoformat(value.strip())


def add_days(start: str, days: int) -> str:
    return (_d(start) + timedelta(days=int(days))).isoformat()


def add_business_days(start: str, days: int) -> str:
    """Move `days` business days from start (negative goes back); start itself isn't counted."""
    current, step, left = _d(start), (1 if int(days) >= 0 else -1), abs(int(days))
    while left:
        current += timedelta(days=step)
        if current.weekday() < 5:
            left -= 1
    return current.isoformat()


def business_days_between(start: str, end: str) -> int:
    """Count business days d with start < d <= end."""
    a, b = _d(start), _d(end)
    sign = 1
    if b < a:
        a, b, sign = b, a, -1
    count, current = 0, a
    while current < b:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return sign * count


def days_between(start: str, end: str) -> int:
    return (_d(end) - _d(start)).days


def weekday(value: str) -> str:
    return WEEKDAYS[_d(value).weekday()]


def business_days_in_range(start: str, end: str) -> list[str]:
    """All business days d with start <= d <= end."""
    a, b = _d(start), _d(end)
    out = []
    while a <= b:
        if a.weekday() < 5:
            out.append(a.isoformat())
        a += timedelta(days=1)
    return out
