"""DeepSeek API prepaid balance.

  GET https://api.deepseek.com/user/balance
  Authorization: Bearer <key>

Returns remaining granted + topped-up balance in CNY and/or USD. There is no
subscription window — this is a prepaid pool, like OpenRouter credits.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .. import secrets
from ..model import AUTH_NEEDED, BALANCE, OK, Meter, Reading, error_reading
from .base import Provider, register

BALANCE_URL = "https://api.deepseek.com/user/balance"


def _meters_from_balance(payload: dict[str, Any]) -> list[Meter]:
    infos = payload.get("balance_infos") or payload.get("data") or []
    if isinstance(infos, dict):
        infos = infos.get("balance_infos") or []
    if not isinstance(infos, list):
        return []
    rows = [item for item in infos if isinstance(item, dict) and item.get("total_balance") is not None]
    if not rows:
        return []
    usd = [item for item in rows if str(item.get("currency") or "").upper() == "USD"]
    chosen = (usd or rows)[0]
    try:
        remaining = float(chosen["total_balance"])
    except (TypeError, ValueError):
        return []
    unit = str(chosen.get("currency") or "USD").upper()
    return [Meter(kind=BALANCE, label="Credits", remaining=remaining, unit=unit)]


@register
class DeepSeek(Provider):
    id = "deepseek"
    label = "DeepSeek"
    source = "http"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        key = secrets.get("deepseek") or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            return error_reading(
                self.id, label,
                "no key stored — `aicredits auth set deepseek`",
                status=AUTH_NEEDED, url=settings.get("url"))
        request = urllib.request.Request(settings.get("balance_url") or BALANCE_URL, headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=int(settings.get("timeout", 15))) as response:
                payload = json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return error_reading(self.id, label, f"{exc.code} — key rejected",
                                     status=AUTH_NEEDED, url=settings.get("url"))
            return error_reading(self.id, label, f"HTTP {exc.code}", url=settings.get("url"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return error_reading(self.id, label, f"{type(exc).__name__}", url=settings.get("url"))

        if not isinstance(payload, dict):
            return error_reading(self.id, label, "balance response was not an object",
                                 url=settings.get("url"))
        meters = _meters_from_balance(payload)
        if not meters:
            return error_reading(self.id, label, "no balance figures in response",
                                 url=settings.get("url"))
        message = None
        if payload.get("is_available") is False:
            message = "balance is not sufficient for API calls"
        return Reading(id=self.id, label=label, status=OK, source=self.source,
                       fetched_at=int(time.time()), url=settings.get("url"),
                       meters=meters, message=message)
