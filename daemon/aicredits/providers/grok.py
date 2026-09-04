"""SuperGrok usage, read from the Grok CLI's unified log.

The CLI logs the billing config it fetches:

  msg "billing: fetched credits config"
  ctx.config = {creditUsagePercent, currentPeriod{type,start,end},
                onDemandCap{val}, onDemandUsed{val}, prepaidBalance{val}}
  ctx.subscriptionTier = "SuperGrok"

This is only as fresh as your last `grok` run, so `fetched_at` comes from the
log line's own timestamp and the UI ages it accordingly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..model import BALANCE, OK, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, last_json_matching, register

LOG = Path.home() / ".grok" / "logs" / "unified.jsonl"
NEEDLE = "billing: fetched credits config"

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


@register
class Grok(Provider):
    id = "grok"
    label = "SuperGrok"
    source = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        log = Path(settings.get("log_path") or LOG).expanduser()
        if not log.exists():
            return error_reading(self.id, label, f"no Grok log at {log}",
                                 url=settings.get("url"))
        record = last_json_matching(log, NEEDLE, lambda o: o.get("msg") == NEEDLE)
        if not record:
            return error_reading(self.id, label, "no billing record logged yet — run `grok` once",
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
