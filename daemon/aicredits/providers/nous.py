"""Nous Portal credits.

The Hermes agent ships as readable Python, which documents the portal's
read-only account endpoints:

  GET /api/oauth/account   entitlement + balance   (hermes_cli/nous_account.py)
  GET /api/billing/state   role-tiered overview    (hermes_cli/nous_billing.py)

Its access token sits unencrypted in ~/.hermes/auth.json, so we can call these
directly. We only ever GET: the same portal API exposes POST /api/billing/charge,
which *buys credits*, and nothing here may go near it.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .. import secrets
from ..model import AUTH_NEEDED, BALANCE, OK, Meter, Reading, error_reading
from .base import Provider, register

AUTH_FILE = Path.home() / ".hermes" / "auth.json"
DEFAULT_BASE = "https://portal.nousresearch.com"
ACCOUNT_PATH = "/api/oauth/account"
BILLING_PATH = "/api/billing/state"


def _token(settings: dict[str, Any]) -> tuple[str | None, str]:
    """(token, base_url) — a user-supplied token wins over the Hermes one."""
    base = settings.get("base_url") or DEFAULT_BASE
    supplied = secrets.get("nous")
    if supplied:
        return supplied, base
    path = Path(settings.get("auth_file") or AUTH_FILE).expanduser()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None, base
    state = (data.get("providers") or {}).get("nous") or {}
    return state.get("access_token"), state.get("portal_base_url") or base


def _refresh_login(settings: dict[str, Any]) -> None:
    """Use Hermes' refresh/locking implementation, keeping secrets off stdout."""
    root = Path(settings.get("hermes_dir") or
                Path.home() / ".hermes" / "hermes-agent").expanduser()
    if "auth_file" in settings:
        return  # Explicit external credentials are not Hermes' managed login.
    try:
        subprocess.run(
            [str(root / "venv/bin/python"), "-c",
             "from hermes_cli.auth import resolve_nous_access_token; "
             "resolve_nous_access_token(refresh_skew_seconds=3600)"],
            cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=int(settings.get("timeout", 15)) + 10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _get(url: str, token: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode() or "{}")


def _number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _meters(payload: dict[str, Any]) -> list[Meter]:
    """Field names taken from what the Hermes billing screens read."""
    subscription = payload.get("subscription")
    subscription = subscription if isinstance(subscription, dict) else {}
    meters: list[Meter] = []

    cap = _number(subscription.get("monthly_credits"), payload.get("monthly_credits"))
    remaining = _number(subscription.get("credits_remaining"),
                        payload.get("subscription_credits_remaining"))
    if remaining is not None or cap is not None:
        meters.append(Meter(kind=BALANCE, label="Subscription", remaining=remaining,
                            total=cap, unit="credits",
                            resets_at=_number(subscription.get("renews_at"),
                                              subscription.get("period_end"))))
    topup = _number(payload.get("purchased_credits_remaining"))
    if topup is not None:
        meters.append(Meter(kind=BALANCE, label="Top-up", remaining=topup, unit="credits"))

    if not meters:
        # OpenRouter-style shape also seen in the Hermes snapshot builder.
        credits = payload.get("credits")
        if isinstance(credits, dict):
            total = _number(credits.get("total_credits"))
            used = _number(credits.get("total_usage"))
            if total is not None and used is not None:
                meters.append(Meter(kind=BALANCE, label="Credits",
                                    remaining=max(0.0, total - used), total=total, unit="USD"))
            elif _number(credits.get("balance")) is not None:
                meters.append(Meter(kind=BALANCE, label="Credits",
                                    remaining=_number(credits.get("balance")), unit="USD"))
    return meters


def _plan(payload: dict[str, Any]) -> str | None:
    subscription = payload.get("subscription")
    subscription = subscription if isinstance(subscription, dict) else {}
    # /api/oauth/account publishes the billing plan here. Numeric tiers and
    # purchasingPower.tierName describe other concepts, not the subscription.
    for value in (subscription.get("plan"), subscription.get("name"), payload.get("plan")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@register
class Nous(Provider):
    id = "nous"
    label = "Nous Portal"
    source = "http"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        if not secrets.get("nous"):
            _refresh_login(settings)
        token, base = _token(settings)
        if not token:
            return error_reading(self.id, label,
                                 "no Nous token — log in with `hermes` or "
                                 "`aicredits auth set nous <token>`",
                                 status=AUTH_NEEDED, url=settings.get("url"))
        timeout = int(settings.get("timeout", 15))
        merged: dict[str, Any] = {}
        errors: list[str] = []
        for path in (BILLING_PATH, ACCOUNT_PATH):
            try:
                payload = _get(base + path, token, timeout)
                if isinstance(payload, dict):
                    merged = {**payload, **merged} if merged else payload
            except urllib.error.HTTPError as exc:
                errors.append(f"{path} -> HTTP {exc.code}")
                if exc.code in (401, 403):
                    return error_reading(self.id, label,
                                         f"token rejected ({exc.code}) after automatic login refresh",
                                         status=AUTH_NEEDED, url=settings.get("url"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                errors.append(f"{path} -> {type(exc).__name__}")
        meters = _meters(merged)
        if not meters:
            return error_reading(self.id, label,
                                 "; ".join(errors) or "portal returned no credit figures",
                                 url=settings.get("url"))
        return Reading(id=self.id, label=label, status=OK, source=self.source,
                       fetched_at=int(time.time()), meters=meters, url=settings.get("url"),
                       plan=_plan(merged))
