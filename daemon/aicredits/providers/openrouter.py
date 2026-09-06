"""OpenRouter credits.

  GET /api/v1/credits -> {data: {total_credits, total_usage}}

Note the key requirement: this endpoint accepts a *management* key. A normal
inference API key returns 403 "Only management keys can perform this operation",
so the error message says so rather than making you guess.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from .. import secrets
from ..model import AUTH_NEEDED, BALANCE, OK, SPEND, Meter, Reading, error_reading
from .base import Provider, register

CREDITS_URL = "https://openrouter.ai/api/v1/credits"
KEY_URL = "https://openrouter.ai/api/v1/key"


def _meters_from_key(data: dict[str, Any]) -> list[Meter]:
    meters: list[Meter] = []
    limit = data.get("limit")
    remaining = data.get("limit_remaining")
    used = data.get("usage")
    try:
        limit_n = float(limit) if limit is not None else None
    except (TypeError, ValueError):
        limit_n = None
    if limit_n and limit_n > 0:
        try:
            remaining_n = float(remaining) if remaining is not None else None
        except (TypeError, ValueError):
            remaining_n = None
        if remaining_n is None and used is not None:
            try:
                remaining_n = max(0.0, limit_n - float(used))
            except (TypeError, ValueError):
                remaining_n = None
        if remaining_n is not None:
            meters.append(Meter(kind=BALANCE, label="Key cap", remaining=remaining_n,
                                total=limit_n, unit="USD",
                                used_pct=round(100.0 * (1.0 - remaining_n / limit_n), 1)))
    for key, label in (("usage_daily", "Today"), ("usage_weekly", "7d"),
                       ("usage_monthly", "30d")):
        try:
            amount = float(data.get(key) or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount:
            meters.append(Meter(kind=SPEND, label=label, amount_usd=round(amount, 2),
                                period=label, unit="USD"))
    return meters


@register
class OpenRouter(Provider):
    id = "openrouter"
    label = "OpenRouter"
    source = "http"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        key = secrets.get("openrouter")
        if not key:
            return error_reading(
                self.id, label,
                "no key stored — `aicredits auth set openrouter <management key>`",
                status=AUTH_NEEDED, url=settings.get("url"))
        request = urllib.request.Request(settings.get("credits_url") or CREDITS_URL, headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=int(settings.get("timeout", 15))) as response:
                payload = json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                return error_reading(self.id, label,
                                     "403 — this endpoint needs a management key, not an API key",
                                     status=AUTH_NEEDED, url=settings.get("url"))
            if exc.code == 401:
                return error_reading(self.id, label, "401 — key rejected",
                                     status=AUTH_NEEDED, url=settings.get("url"))
            return error_reading(self.id, label, f"HTTP {exc.code}", url=settings.get("url"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return error_reading(self.id, label, f"{type(exc).__name__}", url=settings.get("url"))

        data = payload.get("data") or {}
        total = data.get("total_credits")
        used = data.get("total_usage")
        if total is None and used is None:
            return error_reading(self.id, label, "no credit figures in response",
                                 url=settings.get("url"))
        total = float(total or 0.0)
        used = float(used or 0.0)
        meters = [Meter(kind=BALANCE, label="Credits",
                        remaining=max(0.0, total - used), total=total or None, unit="USD")]
        if settings.get("fetch_key", True):
            try:
                key_req = urllib.request.Request(settings.get("key_url") or KEY_URL, headers={
                    "Authorization": f"Bearer {key}",
                    "Accept": "application/json",
                })
                with urllib.request.urlopen(key_req, timeout=min(2, int(settings.get("timeout", 15)))) as response:
                    key_payload = json.loads(response.read().decode() or "{}")
                meters.extend(_meters_from_key(key_payload.get("data") or key_payload))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
                pass
        return Reading(
            id=self.id, label=label, status=OK, source=self.source,
            fetched_at=int(time.time()), url=settings.get("url"),
            meters=meters,
        )
