"""SuperGrok usage, refreshed through the installed Grok client.

Starting Grok's terminal client under a private pseudo-terminal makes the
authenticated client refresh its billing config without sending a prompt or
starting a model turn. The process is stopped as soon as the client logs:

  msg "billing: fetched credits config"
  ctx.config = {creditUsagePercent, currentPeriod{type,start,end},
                onDemandCap{val}, onDemandUsed{val}, prepaidBalance{val}}
  ctx.subscriptionTier = "SuperGrok"

If Grok is missing or fails to initialize, the last logged record remains a
safe fallback and is aged normally by the UI.
"""

from __future__ import annotations

import os
import pty
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from ..model import BALANCE, OK, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, last_json_matching, register

LOG = Path.home() / ".grok" / "logs" / "unified.jsonl"
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
        log = Path(settings.get("log_path") or LOG).expanduser()
        record = None
        # An explicit log_path keeps fixtures deterministic and disables the
        # subprocess unless a caller opts back in with live=true.
        if settings.get("live", "log_path" not in settings):
            record = _refresh_billing_record(
                log, str(settings.get("command") or "grok"),
                int(settings.get("timeout") or REFRESH_TIMEOUT))
        if record is None:
            record = _billing_record(log)
        if record is None and not log.exists():
            return error_reading(self.id, label, f"no Grok log at {log}",
                                 url=settings.get("url"))
        if not record:
            return error_reading(self.id, label, "live refresh failed and no billing record exists",
                                 url=settings.get("url"))
        ctx = record.get("ctx") or {}
        conf = ctx.get("config") or {}
        period = conf.get("currentPeriod") or {}
        meters: list[Meter] = []
        if conf.get("creditUsagePercent") is not None:
            meters.append(Meter(
                kind=WINDOW,
                label=PERIOD_LABELS.get(period.get("type"), "Usage"),
                used_pct=float(conf["creditUsagePercent"]),
                resets_at=iso_to_epoch(period.get("end") or conf.get("billingPeriodEnd")),
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
            return error_reading(self.id, label, "billing record had no usable figures",
                                 url=settings.get("url"))
        return Reading(
            id=self.id, label=label, status=OK, source=self.source,
            fetched_at=iso_to_epoch(record.get("ts")), meters=meters,
            url=settings.get("url"), plan=ctx.get("subscriptionTier"),
        )
