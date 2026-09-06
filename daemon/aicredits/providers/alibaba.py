"""Alibaba Cloud Token Plan (Qwen).

Two sources, in order:

1. `bl usage token-plan --output json` — Alibaba's own Bailian CLI. This is the
   supported path and the only one that knows the plan's rolling quota
   percentage. It needs a *console* token (`bl auth login --console`); the
   plan's sk-sp- model key is not sufficient.

2. Otherwise, consumption from ~/.qwen/usage_record.jsonl (timestamps in
   *milliseconds*), which tells you what you spent but not what is left.

The console's own web gateway is deliberately not used: it sits behind an
anti-automation layer, so scripting it would mean defeating a bot check and
would break on any front-end change.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from ..model import AUTH_NEEDED, OK, SPEND, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, register, window_label

USAGE_RECORD = Path.home() / ".qwen" / "usage_record.jsonl"
CLI = "bl"
LOGIN_HINT = "run `bl auth login --console` to read plan quota"

# Observed shape of `bl usage token-plan --output json`:
#   {"per1WeekPercentage": 0.31039925227231, "per1WeekResetTime": 1788966900000}
# Two traps in that: the "Percentage" field is a *ratio*, and the reset time is
# in milliseconds. Older/other spellings are still handled as a fallback.
_PERIOD_RE = re.compile(r"^per(\d+)(Hour|Day|Week|Month)(Percentage|ResetTime)$")
_PERIOD_MINUTES = {"Hour": 60, "Day": 1440, "Week": 10080}

_PCT_KEYS = ("usedPercent", "used_percent", "usagePercent", "usage_percent",
             "percentUsed", "percent")
_RESET_KEYS = ("resetAt", "reset_at", "resetTime", "nextResetTime",
               "willResetAt", "quotaResetTime")


def _walk(node: Any):
    """Yield every dict in a nested structure, so the quota block is found
    wherever the CLI happens to nest it."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _first(node: dict, keys) -> Any:
    for key in keys:
        if node.get(key) is not None:
            return node[key]
    return None


def _as_epoch(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 1e11 else int(value)
    if isinstance(value, str):
        epoch = iso_to_epoch(value)
        if epoch:
            return epoch
        try:
            number = float(value)
        except ValueError:
            return None
        return int(number / 1000) if number > 1e11 else int(number)
    return None


def _to_percent(value: Any, *, ratio: bool = False) -> float | None:
    """Units follow the response field, never the magnitude of its value."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return round(number * 100 if ratio else number, 2)


def cli_meters(payload: Any) -> tuple[list[Meter], str | None]:
    """Map `bl usage token-plan --output json` into meters."""
    meters: list[Meter] = []
    plan_name = None
    for node in _walk(payload):
        plan_name = plan_name or node.get("planName") or node.get("plan_name")

        # Primary: perNPeriodPercentage / perNPeriodResetTime pairs.
        for key, value in node.items():
            match = _PERIOD_RE.match(key)
            if not match or match.group(3) != "Percentage":
                continue
            count, period = int(match.group(1)), match.group(2)
            pct = _to_percent(value, ratio=True)
            if pct is None:
                continue
            label = (window_label(count * _PERIOD_MINUTES[period])
                     if period in _PERIOD_MINUTES
                     else ("Monthly" if count == 1 else f"{count}-month"))
            meters.append(Meter(
                kind=WINDOW, label=label, used_pct=pct,
                resets_at=_as_epoch(node.get(f"per{count}{period}ResetTime")),
            ))

        # Fallback for other spellings.
        if not meters:
            pct = _to_percent(_first(node, _PCT_KEYS))
            if pct is not None:
                meters.append(Meter(
                    kind=WINDOW,
                    label=str(node.get("quotaName") or node.get("name") or "Quota"),
                    used_pct=pct,
                    resets_at=_as_epoch(_first(node, _RESET_KEYS)),
                ))
    meters.sort(key=lambda m: m.label)
    return meters, plan_name


def _run_cli(settings: dict[str, Any]) -> tuple[Any | None, str | None]:
    """(parsed json, error message)."""
    binary = settings.get("cli") or CLI
    if not shutil.which(binary):
        return None, f"{binary} not on PATH"
    command = [binary, "usage", "token-plan", "--output", "json"]
    for flag, key in (("--console-region", "console_region"),
                      ("--console-site", "console_site"),
                      ("--workspace-id", "workspace_id")):
        if settings.get(key):
            command += [flag, str(settings[key])]
    try:
        proc = subprocess.run(command, capture_output=True, text=True,
                              timeout=int(settings.get("timeout", 30)))
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, type(exc).__name__
    if proc.returncode != 0:
        blob = (proc.stderr or proc.stdout or "").lower()
        if "console" in blob and ("token" in blob or "login" in blob):
            return None, LOGIN_HINT
        return None, (proc.stderr or proc.stdout or "").strip().splitlines()[-1][:120] or "CLI failed"
    try:
        return json.loads(proc.stdout or "{}"), None
    except json.JSONDecodeError:
        return None, "CLI returned non-JSON output"


def _records(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open(errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("models"):
                out.append(obj)
    return out


def _epoch_seconds(record: dict[str, Any]) -> int | None:
    raw = record.get("timestamp") or record.get("startTime")
    if not isinstance(raw, (int, float)):
        return None
    # The Qwen CLI writes milliseconds; anything past year ~2286 in seconds is ms.
    return int(raw / 1000) if raw > 1e11 else int(raw)


def tokens_since(records: list[dict[str, Any]], since: int) -> tuple[int, int]:
    """(total tokens, requests) at or after `since`."""
    tokens = requests = 0
    for record in records:
        ts = _epoch_seconds(record)
        if ts is None or ts < since:
            continue
        for stats in (record.get("models") or {}).values():
            if not isinstance(stats, dict):
                continue
            tokens += int(stats.get("totalTokens") or 0)
            requests += int(stats.get("requests") or 0)
    return tokens, requests


@register
class Alibaba(Provider):
    id = "alibaba"
    label = "Alibaba"
    source = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        if settings.get("use_cli", True):
            payload, error = _run_cli(settings)
            if payload is not None:
                meters, plan = cli_meters(payload)
                if meters:
                    return Reading(id=self.id, label=label, status=OK, source="cli",
                                   fetched_at=int(time.time()), meters=meters,
                                   url=settings.get("url"), plan=plan)
                error = "CLI returned no quota figures"
            reading = self._from_local(settings, label)
            # Keep the local consumption figures, but say why the quota is missing.
            reading.message = f"{error}; showing local consumption only"
            if error == LOGIN_HINT:
                reading.status = AUTH_NEEDED if not reading.meters else reading.status
            return reading
        return self._from_local(settings, label)

    def _from_local(self, settings: dict[str, Any], label: str) -> Reading:
        path = Path(settings.get("usage_record") or USAGE_RECORD).expanduser()
        if not path.exists():
            return error_reading(self.id, label, f"no Qwen usage record at {path}",
                                 url=settings.get("url"))
        records = _records(path)
        if not records:
            return error_reading(self.id, label, "no usage records yet — run `qwen` once",
                                 url=settings.get("url"))
        now = int(time.time())
        newest = max((_epoch_seconds(r) or 0) for r in records) or None
        meters = []
        calls = 0
        for hours, name in ((24, "24h"), (168, "7d")):
            tokens, requests = tokens_since(records, now - hours * 3600)
            calls = max(calls, requests)
            meters.append(Meter(kind=SPEND, label=name, period=name,
                                total=float(tokens), unit="tokens"))
        return Reading(
            id=self.id, label=label, status=OK, source=self.source,
            fetched_at=newest, meters=meters, url=settings.get("url"),
            message=f"{calls} request(s) in 7d",
        )
