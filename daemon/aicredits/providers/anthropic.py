"""Claude usage.

Two paths, in order of preference:

1. `GET https://api.anthropic.com/api/oauth/usage` with Claude Code's own OAuth
   access token, which returns the real 5-hour and weekly subscription windows.
   Current native Claude Code releases keep this in
   `~/.claude/.credentials.json`. A token explicitly stored with
   `aicredits auth set claude` still takes precedence.

2. Otherwise, local transcript accounting: sum the `usage` blocks Claude Code
   writes to ~/.claude/projects/**/*.jsonl and price them at published API
   rates. That measures consumption, not remaining quota — an honest proxy, and
   labelled as an estimate.

Transcripts repeat a record per requestId, so deduplication is mandatory or
every figure doubles.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .. import config as cfg
from .. import secrets
from ..model import OK, SPEND, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, register, window_label

PROJECTS = Path.home() / ".claude" / "projects"
CACHE = cfg.DATA_DIR / "claude_scan.json"
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
CLAUDE_CONFIG = Path.home() / ".claude.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# USD per million tokens (input, output). Prefix match, longest first, so dated
# variants fall back to their family. Override in config: [providers.claude.pricing]
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
CACHE_READ_MULTIPLIER = 0.1        # 0.025 on Fable 5.1; see _cache_read_rate
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.0


def _rates(model: str, overrides: dict[str, Any]) -> tuple[float, float] | None:
    for table in (overrides, PRICING):
        for prefix in sorted(table, key=len, reverse=True):
            if model.startswith(prefix):
                value = table[prefix]
                return (float(value[0]), float(value[1]))
    return None


def _cache_read_rate(model: str, input_rate: float) -> float:
    if model.startswith(("claude-fable-5-1", "claude-mythos-5-1")):
        return 0.25 / 1e6
    return input_rate * CACHE_READ_MULTIPLIER


# ---------------------------------------------------------------- transcripts

def _load_cache() -> dict[str, Any]:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, CACHE)


def _scan_file(path: Path) -> dict[str, dict[str, list[float]]]:
    """Hour-bucketed token totals for one transcript, deduped by requestId."""
    buckets: dict[str, dict[str, list[float]]] = {}
    seen: set[str] = set()
    with path.open(errors="replace") as fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            # The same request is written more than once; count it once.
            key = obj.get("requestId") or message.get("id")
            if key:
                if key in seen:
                    continue
                seen.add(key)
            ts = iso_to_epoch(obj.get("timestamp"))
            if not ts:
                continue
            creation = usage.get("cache_creation") or {}
            hour = str(ts - ts % 3600)
            model = message.get("model") or "unknown"
            slot = buckets.setdefault(hour, {}).setdefault(model, [0.0] * 5)
            slot[0] += usage.get("input_tokens") or 0
            slot[1] += usage.get("output_tokens") or 0
            slot[2] += usage.get("cache_read_input_tokens") or 0
            slot[3] += creation.get("ephemeral_5m_input_tokens") or 0
            slot[4] += creation.get("ephemeral_1h_input_tokens") or 0
    return buckets


def collect(root: Path) -> tuple[dict[str, dict[str, list[float]]], int | None]:
    """Merged hour buckets across every transcript, using an mtime cache."""
    cache = _load_cache()
    fresh: dict[str, Any] = {}
    merged: dict[str, dict[str, list[float]]] = {}
    newest: int | None = None
    for path in sorted(root.glob("*/*.jsonl")):
        try:
            stat = path.stat()
        except OSError:
            continue
        key = str(path)
        entry = cache.get(key)
        if not entry or entry.get("mtime") != int(stat.st_mtime) or entry.get("size") != stat.st_size:
            entry = {"mtime": int(stat.st_mtime), "size": stat.st_size, "buckets": _scan_file(path)}
        fresh[key] = entry
        newest = max(newest or 0, int(stat.st_mtime))
        for hour, models in entry["buckets"].items():
            target = merged.setdefault(hour, {})
            for model, counts in models.items():
                slot = target.setdefault(model, [0.0] * 5)
                for i, value in enumerate(counts):
                    slot[i] += value
    _save_cache(fresh)
    return merged, newest


def cost_since(buckets: dict[str, dict[str, list[float]]], since: int,
               overrides: dict[str, Any]) -> tuple[float, int, set[str]]:
    """(usd, tokens, unpriced models) for everything at or after `since`."""
    usd = 0.0
    tokens = 0
    unpriced: set[str] = set()
    for hour, models in buckets.items():
        if int(hour) + 3600 <= since:
            continue
        for model, (inp, out, read, write5m, write1h) in models.items():
            # "<synthetic>" marks locally generated messages that never hit the
            # API; they cost nothing and are not a missing price.
            if model.startswith("<"):
                continue
            tokens += int(inp + out + read + write5m + write1h)
            rates = _rates(model, overrides)
            if not rates:
                unpriced.add(model)
                continue
            in_rate, out_rate = rates[0] / 1e6, rates[1] / 1e6
            usd += (inp * in_rate + out * out_rate
                    + read * _cache_read_rate(model, in_rate)
                    + write5m * in_rate * CACHE_WRITE_5M
                    + write1h * in_rate * CACHE_WRITE_1H)
    return usd, tokens, unpriced


# ------------------------------------------------------------------ oauth API

def _oauth_usage(token: str, timeout: int = 15) -> dict[str, Any]:
    request = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _local_oauth_token(path: Path = CREDENTIALS) -> str | None:
    """Read Claude Code's access token without ever copying it into our config."""
    try:
        payload = json.loads(path.read_text())
        oauth = payload.get("claudeAiOauth") or {}
        token = oauth.get("accessToken")
        expires_ms = int(oauth.get("expiresAt") or 0)
        if token and (not expires_ms or expires_ms > int(time.time() * 1000)):
            return str(token)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _refresh_local_login(settings: dict[str, Any]) -> str | None:
    """Let Claude rotate its own credentials, without submitting a model turn.

    Empty print input exits with an input error *after* authentication startup.
    Safe mode disables user hooks/plugins; a private cwd avoids project state.
    Credentials remain entirely managed (and locked) by the installed client.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="aicredits-claude-") as cwd:
            subprocess.run(
                [str(settings.get("command") or "claude"), "--safe-mode",
                 "--print", "--tools", ""],
                input="", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                text=True, cwd=cwd, timeout=int(settings.get("timeout") or 30))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return _local_oauth_token()


def _local_plan(path: Path = CREDENTIALS,
                config_path: Path = CLAUDE_CONFIG) -> str | None:
    """Older credentials carry a plan; native clients cache it in the profile."""
    try:
        oauth = json.loads(path.read_text()).get("claudeAiOauth") or {}
        plan = oauth.get("subscriptionType")
        if plan:
            return str(plan)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        account = json.loads(config_path.read_text()).get("oauthAccount") or {}
        # Explicit organization classifications only: billing type and a
        # generic rate-limit tier do not distinguish paid subscription levels.
        return {"claude_pro": "Pro", "claude_max": "Max",
                "claude_team": "Team", "claude_enterprise": "Enterprise",
                "claude_free": "Free"}.get(account.get("organizationType"))
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _meters_from_oauth(payload: dict[str, Any]) -> list[Meter]:
    """Map the usage payload defensively — the shape is undocumented."""
    meters: list[Meter] = []
    # The current endpoint uses named objects. Keep the generic parser below as
    # a fallback for older/alternate payloads, but these names are what lets us
    # distinguish the two headline subscription limits.
    named = (("five_hour", "5h"), ("seven_day", "7d"))
    for key, label in named:
        item = payload.get(key)
        if not isinstance(item, dict) or item.get("utilization") is None:
            continue
        pct = float(item["utilization"])
        meters.append(Meter(
            kind=WINDOW,
            label=label,
            used_pct=pct,  # utilization is already a percentage, including 0–1%.
            resets_at=iso_to_epoch(item.get("resets_at")),
        ))
    if meters:
        return meters

    candidates = payload.get("usage") if isinstance(payload.get("usage"), list) else None
    if candidates is None:
        candidates = [v for v in payload.values() if isinstance(v, dict)]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        pct = next((item[k] for k in ("utilization", "used_percent", "percent_used")
                    if item.get(k) is not None), None)
        if pct is None:
            continue
        resets = item.get("resets_at") or item.get("reset_at")
        meters.append(Meter(
            kind=WINDOW,
            label=str(item.get("name") or window_label(item.get("window_minutes"))),
            used_pct=float(pct),
            resets_at=iso_to_epoch(resets) if isinstance(resets, str) else resets,
        ))
    return meters


def _cached_usage(path: Path = CLAUDE_CONFIG) -> tuple[list[Meter], int | None]:
    """Use Claude Code's last successful usage fetch when the API is offline."""
    try:
        cached = json.loads(path.read_text()).get("cachedUsageUtilization") or {}
        fetched_ms = int(cached.get("fetchedAtMs") or 0)
        meters = _meters_from_oauth(cached.get("utilization") or {})
        return meters, (fetched_ms // 1000 if fetched_ms else None)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return [], None


@register
class Claude(Provider):
    id = "claude"
    label = "Claude"
    source = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        supplied = secrets.get("claude")
        token = supplied or _local_oauth_token()
        if not token:
            token = _refresh_local_login(settings)
        if token:
            try:
                payload = _oauth_usage(token)
                meters = _meters_from_oauth(payload)
                if meters:
                    return Reading(id=self.id, label=label, status=OK, source="http",
                                   fetched_at=int(time.time()), meters=meters,
                                   url=settings.get("url"), plan=_local_plan())
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    # Also recover if a saved override has gone stale: the
                    # configured client's login is a usable fallback.
                    token = _refresh_local_login(settings)
                    if token:
                        try:
                            meters = _meters_from_oauth(_oauth_usage(token))
                            if meters:
                                return Reading(id=self.id, label=label, status=OK,
                                               source="http", fetched_at=int(time.time()),
                                               meters=meters, url=settings.get("url"),
                                               plan=_local_plan())
                        except (urllib.error.URLError, ValueError, TimeoutError):
                            pass
            except (urllib.error.URLError, ValueError, TimeoutError):
                pass
        meters, fetched_at = _cached_usage()
        if meters:
            return Reading(id=self.id, label=label, status=OK, source="local-log",
                           fetched_at=fetched_at, meters=meters, url=settings.get("url"),
                           plan=_local_plan(), message="last usage reported by Claude Code")
        return self._from_transcripts(settings, label)

    def _from_transcripts(self, settings: dict[str, Any], label: str) -> Reading:
        root = Path(settings.get("projects_dir") or PROJECTS).expanduser()
        if not root.is_dir():
            return error_reading(self.id, label, f"no transcript directory at {root}",
                                 url=settings.get("url"))
        buckets, newest = collect(root)
        if not buckets:
            return error_reading(self.id, label, "no usage records in transcripts",
                                 url=settings.get("url"))
        now = int(time.time())
        overrides = settings.get("pricing") or {}
        meters: list[Meter] = []
        unpriced: set[str] = set()
        for hours, name in ((5, "5h"), (168, "7d")):
            usd, tokens, missing = cost_since(buckets, now - hours * 3600, overrides)
            unpriced |= missing
            meters.append(Meter(kind=SPEND, label=name, amount_usd=round(usd, 2),
                                period=name, total=float(tokens), unit="tokens"))
        message = "estimated API-equivalent spend, not subscription quota"
        if unpriced:
            message += f" — unpriced model(s): {', '.join(sorted(unpriced))}"
        return Reading(id=self.id, label=label, status=OK, source="local-log",
                       fetched_at=newest, meters=meters, url=settings.get("url"),
                       message=message)
