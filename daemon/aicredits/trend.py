"""Burn-rate projection: at this pace, when does the meter hit 100% or reset?

Provides subtle pace estimation:
- If consumption exhausts the quota before the window resets: `exhausts_at`.
- If consumption will last through the window: `projected_pct` at reset time.
"""

from __future__ import annotations
from typing import Any


def current_cycle_points(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Extract points belonging to the current cycle by scanning backwards for resets."""
    usable = [(t, v) for t, v in points if v is not None]
    if not usable:
        return []
    # Scan backwards; if pct dropped significantly (>5%), that was the reset into this cycle
    start_idx = 0
    for i in range(len(usable) - 1, 0, -1):
        if usable[i][1] < usable[i - 1][1] - 5.0:
            start_idx = i
            break
    return usable[start_idx:]


def slope_per_second(points: list[tuple[int, float]]) -> float | None:
    """Least-squares slope of pct over time. None if not enough signal."""
    usable = [(t, v) for t, v in points if v is not None]
    if len(usable) < 2:
        return None
    if len(usable) == 2:
        dt = usable[1][0] - usable[0][0]
        return (usable[1][1] - usable[0][1]) / dt if dt > 0 else None

    n = len(usable)
    mean_t = sum(t for t, _ in usable) / n
    mean_v = sum(v for _, v in usable) / n
    denom = sum((t - mean_t) ** 2 for t, _ in usable)
    if denom == 0:
        return None
    return sum((t - mean_t) * (v - mean_v) for t, v in usable) / denom


def project(points: list[tuple[int, float]], current_pct: float, now: int,
            resets_at: int | None) -> dict[str, Any] | None:
    """Estimated exhaustion time, or projected percentage at window reset."""
    if current_pct is None or current_pct >= 100:
        return None
    cycle_pts = current_cycle_points(points)
    slope = slope_per_second(cycle_pts)
    if not slope or slope <= 0:
        return None
    seconds_left = (100.0 - current_pct) / slope
    if seconds_left <= 0:
        return None
    exhausts_at = int(now + seconds_left)
    if resets_at and exhausts_at < resets_at:
        return {"projected_pct": 100, "exhausts_at": exhausts_at}
    if resets_at:
        seconds_to_reset = max(0, resets_at - now)
        projected_pct = min(100.0, current_pct + slope * seconds_to_reset)
        if projected_pct >= current_pct + 1.0:
            return {"projected_pct": round(projected_pct), "exhausts_at": exhausts_at}
    elif seconds_left <= 90 * 86400:
        return {"exhausts_at": exhausts_at}
    return None
