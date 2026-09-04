"""Burn-rate projection: at this pace, when does the meter hit 100%?

Only interesting when exhaustion lands *before* the window resets — otherwise
the honest answer is "you're fine", and we say nothing.
"""

from __future__ import annotations


def slope_per_second(points: list[tuple[int, float]]) -> float | None:
    """Least-squares slope of pct over time. None if not enough signal."""
    usable = [(t, v) for t, v in points if v is not None]
    if len(usable) < 3:
        return None
    n = len(usable)
    mean_t = sum(t for t, _ in usable) / n
    mean_v = sum(v for _, v in usable) / n
    denom = sum((t - mean_t) ** 2 for t, _ in usable)
    if denom == 0:
        return None
    return sum((t - mean_t) * (v - mean_v) for t, v in usable) / denom


def project(points: list[tuple[int, float]], current_pct: float, now: int,
            resets_at: int | None) -> dict[str, int] | None:
    """Estimated exhaustion time, or None when the window outlasts the burn."""
    if current_pct is None or current_pct >= 100:
        return None
    slope = slope_per_second(points)
    if not slope or slope <= 0:
        return None
    seconds_left = (100.0 - current_pct) / slope
    if seconds_left <= 0 or seconds_left > 30 * 86400:
        return None
    exhausts_at = int(now + seconds_left)
    if resets_at and exhausts_at >= resets_at:
        return None
    return {"exhausts_at": exhausts_at}
