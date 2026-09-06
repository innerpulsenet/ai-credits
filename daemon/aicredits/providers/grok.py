"""SuperGrok usage via the CLI billing proxy, then the local log.

`grok login` writes `~/.grok/auth.json`. A GET to
`cli-chat-proxy.grok.com/v1/billing?format=credits` with that bearer returns
the same `creditUsagePercent` the TUI would log. Starting the TUI is reserved
for `source=cli`. If HTTP fails, the last `billing: fetched credits config`
record in `~/.grok/logs/unified.jsonl` remains a safe fallback.
"""

from __future__ import annotations

import json
import os
import pty
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from ..model import BALANCE, OK, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, last_json_matching, register

LOG = Path.home() / ".grok" / "logs" / "unified.jsonl"
AUTH = Path.home() / ".grok" / "auth.json"
BILLING_URL = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
SETTINGS_URL = "https://cli-chat-proxy.grok.com/v1/settings"
NEEDLE = "billing: fetched credits config"
REFRESH_TIMEOUT = 8

PERIOD_LABELS = {
    "USAGE_PERIOD_TYPE_WEEKLY": "Weekly",
    "USAGE_PERIOD_TYPE_MONTHLY": "Monthly",
    "USAGE_PERIOD_TYPE_DAILY": "Daily",
}


def _val(node: Any) -> float:
    if isinstance(node, dict):
        node = node.get("val", 0)
    try:
        return float(node or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(text: str | None) -> int | None:
    if not text:
        return None
    text = text.strip().replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        pass
    match = re.match(r"^(.*?)(\.\d+)(.*?)$", text)
    if match:
        frac = match.group(2)[:7]
        try:
            return int(datetime.fromisoformat(match.group(1) + frac + match.group(3)).timestamp())
        except ValueError:
            pass
    return iso_to_epoch(text)


def _oauth_token(path: Path, now: int | None = None) -> tuple[str | None, str | None]:
    """Return (bearer, plan hint) from grok login's auth.json."""
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    now = now if now is not None else int(time.time())
    entries = [(key, value) for key, value in payload.items() if isinstance(value, dict)]
    entries.sort(key=lambda item: (0 if str(item[0]).startswith("https://auth.x.ai::") else 1))
    for key, entry in entries:
        token = entry.get("key")
        if not token:
            continue
        expires = _parse_dt(entry.get("expires_at"))
        if expires is not None and expires <= now:
            continue
        plan = "SuperGrok" if str(key).startswith("https://auth.x.ai::") else None
        return str(token), plan
    return None, None


def _fetch_proxy_billing(token: str, settings: dict[str, Any]) -> tuple[dict[str, Any], str | None] | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "x-xai-token-auth": "xai-grok-cli",
        "Accept": "application/json",
        "User-Agent": "aicredits/0.1",
    }
    timeout = int(settings.get("timeout") or REFRESH_TIMEOUT)
    try:
        request = urllib.request.Request(str(settings.get("billing_url") or BILLING_URL),
                                         headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode() or "{}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    config = payload.get("config") if isinstance(payload, dict) else None
    if not isinstance(config, dict):
        return None
    plan = payload.get("subscriptionTier") if isinstance(payload, dict) else None
    try:
        request = urllib.request.Request(str(settings.get("settings_url") or SETTINGS_URL),
                                         headers=headers)
        with urllib.request.urlopen(request, timeout=min(2, timeout)) as response:
            extra = json.loads(response.read().decode() or "{}")
        if isinstance(extra, dict) and extra.get("subscription_tier_display"):
            plan = extra["subscription_tier_display"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        pass
    return config, str(plan) if plan else None


def _reading_from_config(conf: dict[str, Any], plan: str | None, fetched_at: int | None,
                         url: str | None, *, source: str = "http",
                         label: str = "SuperGrok") -> Reading | None:
    period = conf.get("currentPeriod") or {}
    meters: list[Meter] = []
    percent = conf.get("creditUsagePercent")
    if percent is None:
        cap = _val(conf.get("onDemandCap"))
        used = _val(conf.get("onDemandUsed"))
        if cap > 0:
            percent = used / cap * 100.0
    if percent is not None:
        meters.append(Meter(
            kind=WINDOW,
            label=PERIOD_LABELS.get(str(period.get("type") or ""), "Usage"),
            used_pct=float(percent),
            resets_at=_parse_dt(period.get("end") or conf.get("billingPeriodEnd")),
        ))
    prepaid = _val(conf.get("prepaidBalance"))
    if prepaid:
        meters.append(Meter(kind=BALANCE, label="Prepaid", remaining=prepaid, unit="credits"))
    cap = _val(conf.get("onDemandCap"))
    if cap:
        meters.append(Meter(kind=BALANCE, label="On-demand",
                            remaining=cap - _val(conf.get("onDemandUsed")),
                            total=cap, unit="credits"))
    if not meters:
        return None
    return Reading(id="grok", label=label, status=OK, source=source,
                   fetched_at=fetched_at, meters=meters, url=url, plan=plan)


def _billing_record(log: Path) -> dict[str, Any] | None:
    if not log.exists():
        return None
    return last_json_matching(log, NEEDLE, lambda obj: obj.get("msg") == NEEDLE)


def _refresh_billing_record(log: Path, command: str = "grok",
                            timeout: int = REFRESH_TIMEOUT) -> dict[str, Any] | None:
    """Start Grok invisibly and wait for the fresh billing record it fetches."""
    executable = shutil.which(command) if "/" not in command else command
    if not executable:
        return None
    started_at = int(time.time())
    process: subprocess.Popen[bytes] | None = None
    master: int | None = None
    slave: int | None = None
    try:
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [executable, "--no-alt-screen"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            close_fds=True,
        )
        os.close(slave)
        slave = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = _billing_record(log)
            if record and (iso_to_epoch(record.get("ts")) or 0) >= started_at - 1:
                return record
            if process.poll() is not None:
                break
            time.sleep(0.1)
    except OSError:
        return None
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if slave is not None:
            os.close(slave)
        if master is not None:
            os.close(master)
    return None


@register
class Grok(Provider):
    id = "grok"
    label = "SuperGrok"
    source = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        url = settings.get("url")
        log = Path(settings.get("log_path") or LOG).expanduser()
        source = str(settings.get("source") or "auto")
        live = bool(settings.get("live", "log_path" not in settings))
        if live and source != "cli":
            token, plan_hint = _oauth_token(Path(settings.get("auth_file") or AUTH).expanduser())
            if token:
                fetched = _fetch_proxy_billing(token, settings)
                if fetched:
                    conf, plan = fetched
                    reading = _reading_from_config(conf, plan or plan_hint, int(time.time()), url,
                                                   label=label)
                    if reading:
                        return reading
        record = None
        if live and source == "cli":
            record = _refresh_billing_record(
                log, str(settings.get("command") or "grok"),
                int(settings.get("timeout") or REFRESH_TIMEOUT))
        if record is None:
            record = _billing_record(log)
        if record is None and not log.exists():
            return error_reading(self.id, label, f"no Grok log at {log}", url=url)
        if not record:
            return error_reading(self.id, label, "live refresh failed and no billing record exists",
                                 url=url)
        ctx = record.get("ctx") or {}
        reading = _reading_from_config(ctx.get("config") or {}, ctx.get("subscriptionTier"),
                                       iso_to_epoch(record.get("ts")), url,
                                       source=self.source, label=label)
        return reading or error_reading(self.id, label, "billing record had no usable figures",
                                        url=url)
