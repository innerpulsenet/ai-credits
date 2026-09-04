"""Codex / ChatGPT plan limits, read from the CLI's own session rollouts.

Codex writes a `token_count` event on every turn carrying the exact rate-limit
windows the server returned, so there is nothing to fetch over the network:

  payload.rate_limits = {primary:   {used_percent, window_minutes: 300,   resets_at},
                         secondary: {used_percent, window_minutes: 10080, resets_at},
                         credits:   {has_credits, unlimited, balance}, plan_type}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..model import BALANCE, OK, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, register, tail_lines, window_label
import json

SESSIONS = Path.home() / ".codex" / "sessions"


def _newest_sessions(root: Path, count: int = 5) -> list[Path]:
    files = sorted(root.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:count]


def _latest_rate_limits(root: Path) -> tuple[dict, str] | None:
    for path in _newest_sessions(root):
        for line in tail_lines(path):
            if '"rate_limits"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            limits = (obj.get("payload") or {}).get("rate_limits")
            if limits:
                return limits, obj.get("timestamp", "")
    return None


@register
class Codex(Provider):
    id = "codex"
    label = "Codex"
    source = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        root = Path(settings.get("sessions_dir") or SESSIONS).expanduser()
        if not root.is_dir():
            return error_reading(self.id, settings.get("label", self.label),
                                 f"no session directory at {root}", url=settings.get("url"))
        found = _latest_rate_limits(root)
        if not found:
            return error_reading(self.id, settings.get("label", self.label),
                                 "no rate_limits in recent Codex sessions", url=settings.get("url"))
        limits, timestamp = found
        meters: list[Meter] = []
        for key in ("primary", "secondary"):
            window = limits.get(key)
            if not window or window.get("used_percent") is None:
                continue
            meters.append(Meter(
                kind=WINDOW,
                label=window_label(window.get("window_minutes")),
                used_pct=float(window["used_percent"]),
                resets_at=window.get("resets_at"),
            ))
        credits = limits.get("credits") or {}
        if credits.get("has_credits") and not credits.get("unlimited"):
            try:
                balance = float(credits.get("balance") or 0)
            except (TypeError, ValueError):
                balance = 0.0
            meters.append(Meter(kind=BALANCE, label="Credits", remaining=balance, unit="credits"))
        if not meters:
            return error_reading(self.id, settings.get("label", self.label),
                                 "rate_limits present but empty", url=settings.get("url"))
        return Reading(
            id=self.id,
            label=settings.get("label", self.label),
            status=OK,
            source=self.source,
            fetched_at=iso_to_epoch(timestamp),
            meters=meters,
            url=settings.get("url"),
            plan=limits.get("plan_type"),
        )
