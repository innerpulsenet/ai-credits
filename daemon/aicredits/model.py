"""Normalized data model shared by every provider adapter and the plasmoid.

Three meter kinds cover all providers:

  window   rolling quota that resets   -> used_pct + resets_at
  balance  prepaid pool                -> remaining / total / unit
  spend    period-to-date cost         -> amount_usd / period
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# Provider status values. The UI renders each distinctly: a provider we cannot
# read must never look like a provider sitting at 0%.
OK = "ok"
STALE = "stale"
AUTH_NEEDED = "auth_needed"
ERROR = "error"
MANUAL = "manual"

WINDOW = "window"
BALANCE = "balance"
SPEND = "spend"


@dataclass
class Meter:
    kind: str
    label: str
    used_pct: float | None = None
    resets_at: int | None = None
    remaining: float | None = None
    total: float | None = None
    unit: str | None = None
    amount_usd: float | None = None
    period: str | None = None
    projection: dict[str, Any] | None = None
    # True when resets_at has already passed: the figure describes a window
    # that has since rolled over, so it is history, not current state.
    expired: bool = False

    def pct(self) -> float | None:
        """Percentage consumed, uniform across kinds, for the tray ring."""
        if self.used_pct is not None:
            return self.used_pct
        # Only a *known* remaining figure yields a percentage. Treating an
        # unknown remaining as zero would report a fresh, unused grant as 100%
        # consumed and fire a critical alert on it.
        if self.kind == BALANCE and self.total and self.remaining is not None:
            return max(0.0, 100.0 * (1.0 - self.remaining / self.total))
        return None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "label": self.label}
        for name in ("used_pct", "resets_at", "remaining", "total", "unit",
                     "amount_usd", "period", "projection"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        if self.expired:
            out["expired"] = True
        pct = self.pct()
        if pct is not None and self.used_pct is None:
            out["used_pct"] = round(pct, 1)
        return out


@dataclass
class Reading:
    id: str
    label: str
    status: str = OK
    source: str = "local-log"          # local-log | http | manual
    fetched_at: int | None = None      # when the *data* was produced, not polled
    meters: list[Meter] = field(default_factory=list)
    message: str | None = None         # human-readable error / hint
    url: str | None = None             # dashboard to open on click
    plan: str | None = None

    def worst_pct(self) -> float | None:
        # An expired window describes a period that has already rolled over;
        # letting it drive the tray ring would paint the panel red over history.
        values = [m.pct() for m in self.meters if m.pct() is not None and not m.expired]
        return max(values) if values else None

    def worst_meter(self) -> Meter | None:
        candidates = [m for m in self.meters if m.pct() is not None and not m.expired]
        return max(candidates, key=lambda meter: meter.pct() or 0) if candidates else None

    def to_json(self, now: int | None = None) -> dict[str, Any]:
        now = now or int(time.time())
        out: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "source": self.source,
            "meters": [m.to_json() for m in self.meters],
        }
        if self.fetched_at:
            out["fetched_at"] = self.fetched_at
            out["stale_seconds"] = max(0, now - self.fetched_at)
        for name in ("message", "url", "plan"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        pct = self.worst_pct()
        if pct is not None:
            out["worst_pct"] = round(pct, 1)
            worst = self.worst_meter()
            if worst:
                out["worst_label"] = worst.label
        return out


def error_reading(pid: str, label: str, message: str, *, status: str = ERROR,
                  url: str | None = None) -> Reading:
    return Reading(id=pid, label=label, status=status, message=message, url=url)
