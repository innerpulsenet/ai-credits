"""Z.ai ZCode (GLM coding plan) quota.

Preferred source is the coding-plan monitor endpoint, which is the only thing
that knows the rolling 5-hour and weekly token windows:

  GET https://api.z.ai/api/monitor/usage/quota/limit
  Authorization: <key>          (no "Bearer " prefix)

It needs a Z.ai API key (`aicredits auth set zai <key>`); ZCode's own OAuth
token is Electron-encrypted and unusable. Without a key we fall back to the
logs below, which only ever carry MCP quota and the plan grant.

ZCode stores its OAuth token encrypted (`enc:v1:…`, Electron safeStorage keyed
by the OS keyring), so calling https://zcode.z.ai/api/v1/… ourselves would mean
reimplementing that decryption. We don't need to: ZCode logs the full response
bodies it receives, so we read those instead — no token handling, no second
caller hitting the vendor's API, at the cost of freshness (the figures are as
new as your last ZCode run).

  官方 MCP 額度響應   {"body":"{...data:{level,next_refresh_at,total_usage:{used,limit,remaining}}}"}
  billing/balance    {"payload":{"data":{"plans":[{name,status,ends_at,entitlements:[…]}],"balances":[…]}}}
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from .. import secrets
from ..model import BALANCE, OK, WINDOW, Meter, Reading, error_reading
from .base import Provider, register, tail_lines, window_label

QUOTA_URL = "https://api.z.ai/api/monitor/usage/quota/limit"
CN_QUOTA_URL = "https://open.bigmodel.cn/api/monitor/usage/quota/limit"

LOG_DIR = Path.home() / ".zcode" / "v2" / "logs"
MCP_MARKER = "MCP"
MCP_RESPONSE = "官方 MCP 额度响应"      # "official MCP quota response"
BALANCE_MARKER = "billing/balance"

_DECODER = json.JSONDecoder()


def _embedded_json(line: str, marker: str) -> dict | None:
    """Pull the JSON object that follows `marker` on a log line."""
    at = line.find(marker)
    if at < 0:
        return None
    brace = line.find("{", at)
    if brace < 0:
        return None
    try:
        obj, _ = _DECODER.raw_decode(line[brace:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _log_files(root: Path) -> list[Path]:
    return sorted(root.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)


def _scan(root: Path, marker: str, limit_files: int = 6) -> dict | None:
    """Newest log record containing `marker`, searching backwards."""
    for path in _log_files(root)[:limit_files]:
        for line in tail_lines(path):
            if marker not in line:
                continue
            obj = _embedded_json(line, marker)
            if obj:
                return obj
    return None


def _mcp_meter(root: Path) -> tuple[Meter | None, int | None, str | None]:
    record = _scan(root, MCP_RESPONSE)
    if not record:
        return None, None, None
    try:
        body = json.loads(record.get("body") or "{}")
    except json.JSONDecodeError:
        return None, None, None
    data = body.get("data") or {}
    usage = data.get("total_usage") or {}
    if usage.get("limit") is None:
        return None, data.get("server_time"), data.get("level")
    meter = Meter(
        kind=BALANCE, label="MCP",
        remaining=float(usage.get("remaining", 0)),
        total=float(usage["limit"]),
        unit="calls",
        resets_at=data.get("next_refresh_at"),
    )
    return meter, data.get("server_time"), data.get("level")


# Field names seen (or plausibly used) in a plan balance entry, most specific first.
_REMAINING_KEYS = ("remaining", "remaining_units", "balance", "available")
_TOTAL_KEYS = ("limit", "total", "grant_units", "total_units")


def _plan_meters(root: Path) -> tuple[list[Meter], int | None]:
    record = _scan(root, BALANCE_MARKER)
    if not record:
        return [], None
    data = ((record.get("payload") or {}).get("data")) or {}
    meters: list[Meter] = []
    for entry in data.get("balances") or []:
        remaining = next((entry[k] for k in _REMAINING_KEYS if entry.get(k) is not None), None)
        total = next((entry[k] for k in _TOTAL_KEYS if entry.get(k) is not None), None)
        if remaining is None and total is None:
            continue
        meters.append(Meter(
            kind=BALANCE,
            label=str(entry.get("show_name") or entry.get("name") or "Plan"),
            remaining=float(remaining) if remaining is not None else None,
            total=float(total) if total is not None else None,
            unit=str(entry.get("unit_type") or "units"),
            resets_at=entry.get("ends_at") or entry.get("period_end"),
        ))
    if not meters:
        # No consumption figures published; show the active grant and its expiry
        # so the row still says something true rather than disappearing.
        for plan in data.get("plans") or []:
            if plan.get("status") != "active":
                continue
            for ent in plan.get("entitlements") or []:
                meters.append(Meter(
                    kind=BALANCE,
                    label=str(ent.get("show_name") or plan.get("name") or "Plan"),
                    total=float(ent["grant_units"]) if ent.get("grant_units") else None,
                    unit=str(ent.get("unit_type") or "units"),
                    resets_at=plan.get("ends_at"),
                ))
    return meters, data.get("server_time")


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _epoch(value: Any) -> int | None:
    number = _num(value)
    if number is None:
        return None
    return int(number / 1000) if number > 1e11 else int(number)


# Verified response (2026-09-04):
#   {"code":200,"data":{"level":"lite","limits":[
#     {"type":"CREDIT_LIMIT","unit":3,"number":5,"usage":2000,"currentValue":0,
#      "remaining":2000,"percentage":0},
#     {"type":"CREDIT_LIMIT","unit":6,"number":1,"usage":10000,"currentValue":7515,
#      "remaining":2484,"percentage":75,"nextResetTime":1788827431997}]}}
#
# `usage` is the limit and `currentValue` the amount consumed — not the other way
# round. The window is encoded as unit+number, and the short window carries no
# nextResetTime, so the unit map is the only way to label it.
UNIT_MINUTES = {3: 60, 6: 10080}        # verified: 3 = hours, 6 = weeks
_CREDIT_TYPES = ("CREDIT_LIMIT", "TOKENS_LIMIT")


def _label_for(node: dict, reset_at: int | None, now: int) -> str:
    minutes = UNIT_MINUTES.get(node.get("unit"))
    number = _num(node.get("number"))
    if minutes and number:
        return window_label(int(minutes * number))
    # Unknown unit: fall back to how far off the reset is.
    if reset_at:
        hours = (reset_at - now) / 3600
        if 0 < hours <= 24:
            return window_label(300)
        if hours <= 24 * 8:
            return window_label(10080)
    return "Quota"


def quota_meters(payload: Any, now: int | None = None) -> tuple[list[Meter], str | None]:
    """Map /api/monitor/usage/quota/limit into meters plus the plan level."""
    now = now or int(time.time())
    meters: list[Meter] = []
    level = None
    for node in _walk(payload):
        if level is None and isinstance(node.get("level"), str):
            level = node["level"]
        kind = str(node.get("type") or "")
        if kind not in _CREDIT_TYPES and kind != "TIME_LIMIT":
            continue
        reset_at = _epoch(node.get("nextResetTime"))
        total = _num(node.get("usage"))
        used = _num(node.get("currentValue"))
        remaining = _num(node.get("remaining"))
        if remaining is None and total is not None and used is not None:
            remaining = total - used
        # Prefer the computed ratio: `percentage` is rounded to whole numbers.
        if total and used is not None:
            pct = round(100.0 * used / total, 1)
        else:
            raw = _num(node.get("percentage"))
            pct = None if raw is None else round(raw * 100 if 0 < raw <= 1 else raw, 1)
        if pct is None:
            continue
        if kind == "TIME_LIMIT":
            if not used:            # an untouched MCP allowance is just noise
                continue
            meters.append(Meter(kind=BALANCE, label="MCP", used_pct=pct,
                                remaining=remaining, total=total, unit="calls",
                                resets_at=reset_at))
            continue
        meters.append(Meter(kind=WINDOW, label=_label_for(node, reset_at, now),
                            used_pct=pct, remaining=remaining, total=total,
                            unit="credits", resets_at=reset_at))
    return meters, level


def _fetch_quota(settings: dict[str, Any]) -> tuple[list[Meter], str | None, str | None]:
    key = secrets.get("zai")
    if not key:
        return [], None, "no Z.ai key — `aicredits auth set zai` for the 5h/weekly credit windows"
    url = settings.get("quota_url") or (CN_QUOTA_URL if settings.get("cn") else QUOTA_URL)
    request = urllib.request.Request(url, headers={
        "Authorization": key,          # this API takes a bare token, not Bearer
        "Accept": "application/json",
        "Accept-Language": "en-US,en",
    })
    try:
        with urllib.request.urlopen(request, timeout=int(settings.get("timeout", 15))) as response:
            payload = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        return [], None, f"quota endpoint returned HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], None, type(exc).__name__
    meters, level = quota_meters(payload)
    if not meters:
        return [], None, "quota endpoint returned no recognisable limits"
    return meters, level, None


@register
class Zai(Provider):
    id = "zai"
    label = "ZCode GLM"
    source = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        root = Path(settings.get("log_dir") or LOG_DIR).expanduser()
        if not root.is_dir():
            return error_reading(self.id, label, f"no ZCode log directory at {root}",
                                 url=settings.get("url"))
        quota, quota_level, quota_error = _fetch_quota(settings)
        if quota:
            return Reading(id=self.id, label=label, status=OK, source="http",
                           fetched_at=int(time.time()), meters=quota,
                           url=settings.get("url"), plan=quota_level)

        mcp, mcp_time, level = _mcp_meter(root)
        plan_meters, plan_time = _plan_meters(root)
        # Drop an untouched MCP allowance entirely, and rank it behind the plan
        # grant otherwise: for anyone not using MCP through Z.ai it is a
        # permanent 0% that crowds out the figures that matter.
        if mcp is not None and mcp.total and mcp.remaining == mcp.total:
            mcp = None
        meters = plan_meters + ([mcp] if mcp else [])
        if not meters:
            return error_reading(self.id, label,
                                 "no quota records in ZCode logs — open ZCode once",
                                 url=settings.get("url"))
        fetched = max([t for t in (mcp_time, plan_time) if t] or [0]) or None
        return Reading(id=self.id, label=label, status=OK, source=self.source,
                       fetched_at=fetched, meters=meters, url=settings.get("url"),
                       plan=level, message=quota_error)
