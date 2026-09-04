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
from ..model import AUTH_NEEDED, BALANCE, OK, Meter, Reading, error_reading
from .base import Provider, register

CREDITS_URL = "https://openrouter.ai/api/v1/credits"


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
        return Reading(
            id=self.id, label=label, status=OK, source=self.source,
            fetched_at=int(time.time()), url=settings.get("url"),
            meters=[Meter(kind=BALANCE, label="Credits",
                          remaining=max(0.0, total - used), total=total or None, unit="USD")],
        )
