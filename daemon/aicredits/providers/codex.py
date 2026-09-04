"""Codex / ChatGPT plan limits.

The preferred path asks Codex App Server for `account/rateLimits/read`. This is
the same structured interface used by rich Codex clients and does not start a
model turn. If the installed client is unavailable or the request fails, fall
back to the last `token_count` event in the CLI's session rollouts.

  payload.rate_limits = {primary:   {used_percent, window_minutes: 300,   resets_at},
                         secondary: {used_percent, window_minutes: 10080, resets_at},
                         credits:   {has_credits, unlimited, balance}, plan_type}
"""

from __future__ import annotations

import json
import selectors
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from ..model import BALANCE, OK, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, register, tail_lines, window_label

SESSIONS = Path.home() / ".codex" / "sessions"
APP_SERVER_TIMEOUT = 8


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


def _app_server_rate_limits(command: str = "codex",
                            timeout: int = APP_SERVER_TIMEOUT) -> dict[str, Any] | None:
    """Fetch a live snapshot through Codex's newline-delimited JSON-RPC API."""
    executable = shutil.which(command) if "/" not in command else command
    if not executable:
        return None
    requests = "\n".join((
        json.dumps({
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "aicredits", "version": "0.1"}},
        }),
        json.dumps({"id": 2, "method": "account/rateLimits/read"}),
        "",
    ))
    process: subprocess.Popen[str] | None = None
    selector: selectors.BaseSelector | None = None
    try:
        process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(requests)
        process.stdin.flush()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0, deadline - time.monotonic())
            if not selector.select(timeout=min(0.25, remaining)):
                if process.poll() is not None:
                    break
                continue
            line = process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") != 2 or not isinstance(message.get("result"), dict):
                continue
            payload = message["result"]
            buckets = payload.get("rateLimitsByLimitId")
            if isinstance(buckets, dict) and isinstance(buckets.get("codex"), dict):
                return buckets["codex"]
            limits = payload.get("rateLimits")
            return limits if isinstance(limits, dict) else None
    except (OSError, BrokenPipeError):
        pass
    finally:
        if selector is not None:
            selector.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return None


def _normalize_live_limits(limits: dict[str, Any]) -> dict[str, Any]:
    """Translate App Server's camelCase response into the rollout shape."""
    out: dict[str, Any] = {}
    for key in ("primary", "secondary"):
        window = limits.get(key)
        if not isinstance(window, dict):
            continue
        out[key] = {
            "used_percent": window.get("usedPercent"),
            "window_minutes": window.get("windowDurationMins"),
            "resets_at": window.get("resetsAt"),
        }
    credits = limits.get("credits")
    if isinstance(credits, dict):
        out["credits"] = {
            "has_credits": credits.get("hasCredits"),
            "unlimited": credits.get("unlimited"),
            "balance": credits.get("balance"),
        }
    out["plan_type"] = limits.get("planType")
    return out


def _reading_from_limits(limits: dict[str, Any], label: str, url: str | None,
                         fetched_at: int | None, source: str) -> Reading | None:
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
        return None
    return Reading(id="codex", label=label, status=OK, source=source,
                   fetched_at=fetched_at, meters=meters, url=url,
                   plan=limits.get("plan_type"))


@register
class Codex(Provider):
    id = "codex"
    label = "Codex"
    source = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        url = settings.get("url")
        # An explicit sessions_dir is also the fixture/testing escape hatch.
        if settings.get("live", True) and "sessions_dir" not in settings:
            live = _app_server_rate_limits(str(settings.get("command") or "codex"),
                                           int(settings.get("timeout") or APP_SERVER_TIMEOUT))
            if live:
                reading = _reading_from_limits(_normalize_live_limits(live), label, url,
                                               int(time.time()), "http")
                if reading:
                    return reading

        root = Path(settings.get("sessions_dir") or SESSIONS).expanduser()
        if not root.is_dir():
            return error_reading(self.id, label, f"no session directory at {root}", url=url)
        found = _latest_rate_limits(root)
        if not found:
            return error_reading(self.id, label, "live query failed and no rate_limits exist "
                                 "in recent Codex sessions", url=url)
        limits, timestamp = found
        reading = _reading_from_limits(limits, label, url, iso_to_epoch(timestamp), self.source)
        return reading or error_reading(self.id, label, "rate_limits present but empty", url=url)
