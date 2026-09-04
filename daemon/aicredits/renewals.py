"""Subscription renewal dates and costs — the 'what am I paying for' half.

Nothing derives these from an API; they live in config.toml:

  [providers.claude.renewal]
  date = "2026-09-20"   # any past or future occurrence
  cost_usd = 100.0
  cadence = "monthly"   # monthly | annual | weekly
"""

from __future__ import annotations

import datetime as dt
from typing import Any

CADENCE_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12, "yearly": 12}


def _add_months(day: dt.date, months: int) -> dt.date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp to the last valid day (a 31st renewal in a 30-day month).
    last = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return dt.date(year, month, min(day.day, last))


def next_occurrence(anchor: str, cadence: str, today: dt.date | None = None) -> dt.date | None:
    today = today or dt.date.today()
    try:
        day = dt.date.fromisoformat(anchor)
    except (TypeError, ValueError):
        return None
    cadence = (cadence or "monthly").lower()
    if cadence == "weekly":
        while day < today:
            day += dt.timedelta(days=7)
        return day
    # Step from the original anchor each time: a subscription anchored on the
    # 31st bills on the 28th in February and back on the 31st in March, so
    # accumulating onto an already-clamped date would drift the day earlier.
    months = CADENCE_MONTHS.get(cadence, 1)
    anchor_day = day
    step = 0
    while day < today and step < 600:
        step += 1
        day = _add_months(anchor_day, months * step)
    return day


def monthly_equivalent(cost: float, cadence: str) -> float:
    cadence = (cadence or "monthly").lower()
    if cadence == "weekly":
        return cost * 52 / 12
    return cost / CADENCE_MONTHS.get(cadence, 1)


def describe(settings: dict[str, Any], today: dt.date | None = None) -> dict[str, Any] | None:
    renewal = settings.get("renewal")
    if not isinstance(renewal, dict) or not renewal.get("date"):
        return None
    cadence = renewal.get("cadence", "monthly")
    day = next_occurrence(renewal["date"], cadence, today)
    if not day:
        return None
    cost = float(renewal.get("cost_usd") or 0)
    return {
        "date": day.isoformat(),
        "days_until": (day - (today or dt.date.today())).days,
        "cost_usd": cost,
        "cadence": cadence,
        "monthly_usd": round(monthly_equivalent(cost, cadence), 2),
    }
