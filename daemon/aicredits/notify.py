"""KDE notifications with hysteresis.

Alerts are keyed by (provider, meter, level, window) so crossing 80% fires once
per rolling window, not once per poll.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any

from .model import OK

APP = "AI Credits"


def _send(summary: str, body: str, urgency: str = "normal", icon: str = "applications-development") -> None:
    if not shutil.which("notify-send"):
        return
    subprocess.run(
        ["notify-send", "-a", APP, "-i", icon, "-u", urgency, summary, body],
        check=False, capture_output=True,
    )


def _fired(conn, provider: str, meter: str, level: str, window_key: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM alerts WHERE provider=? AND meter=? AND level=? AND window_key=?",
        (provider, meter, level, window_key)).fetchone()
    return row is not None


def _mark(conn, provider: str, meter: str, level: str, window_key: str, now: int) -> None:
    conn.execute("INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?)",
                 (provider, meter, level, window_key, now))
    conn.commit()


def check(conn, reading, general: dict[str, Any], now: int) -> list[str]:
    """Fire threshold alerts for one reading. Returns what was sent."""
    if not general.get("notify", True) or reading.status != OK:
        return []
    warn = float(general.get("warn_pct", 80))
    critical = float(general.get("critical_pct", 95))
    sent = []
    for meter in reading.meters:
        pct = meter.pct()
        if pct is None:
            continue
        window_key = str(meter.resets_at or "static")
        for level, threshold, urgency in (("critical", critical, "critical"), ("warn", warn, "normal")):
            if pct < threshold:
                continue
            # Crossing critical implies warn; mark both so we don't double-fire.
            if _fired(conn, reading.id, meter.label, level, window_key):
                break
            _send(f"{reading.label}: {pct:.0f}% of {meter.label} used",
                  _body(reading, meter, now), urgency)
            _mark(conn, reading.id, meter.label, level, window_key, now)
            if level == "critical":
                _mark(conn, reading.id, meter.label, "warn", window_key, now)
            sent.append(f"{reading.id}/{meter.label}/{level}")
            break
    return sent


def _body(reading, meter, now: int) -> str:
    parts = []
    if meter.resets_at:
        remaining = meter.resets_at - now
        if remaining > 0:
            hours = remaining / 3600
            parts.append(f"resets in {hours:.0f}h" if hours >= 1 else f"resets in {remaining // 60}m")
    if meter.remaining is not None:
        parts.append(f"{meter.remaining:g} {meter.unit or ''}".strip() + " left")
    if reading.plan:
        parts.append(f"plan: {reading.plan}")
    return " · ".join(parts) or "Check the dashboard for details."


def stale_alert(conn, pid: str, label: str, last_ok: int | None, now: int, after: int) -> bool:
    """One alert when a provider has been unreadable for longer than `after`."""
    if last_ok and now - last_ok < after:
        return False
    window_key = time.strftime("%Y-%m-%d", time.localtime(now))
    if _fired(conn, pid, "*", "unreadable", window_key):
        return False
    _send(f"{label}: usage data is stale",
          "Could not read fresh usage for over a day.", "low", "dialog-warning")
    _mark(conn, pid, "*", "unreadable", window_key, now)
    return True
