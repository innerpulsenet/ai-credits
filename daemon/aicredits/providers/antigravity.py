"""Google Antigravity / AI Pro quota.

Antigravity's own CLI will print the quota table non-interactively:

    agy --print "/usage" --output-format text

which emits one tab-separated row per limit:

    Gemini Models\tWeekly Limit Remaining\t81%\t2026-09-10T23:31:47Z
    Gemini Models\tFive Hour Limit Remaining\t100%\t2026-09-05T01:16:55Z
    Claude and GPT models\tWeekly Limit Remaining\t100%\t2026-09-11T20:16:55Z

The trap: those percentages are *remaining*, the inverse of every other
provider here, so they are flipped on the way in. `/usage` is the subscription
command; `/credits` covers pay-as-you-go credits and exits immediately on a
subscription account.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from typing import Any

from ..model import AUTH_NEEDED, OK, WINDOW, Meter, Reading, error_reading
from .base import Provider, iso_to_epoch, register

CLI = "agy"
USAGE_ARGS = ["--print", "/usage", "--output-format", "text"]

_PCT = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*$")


def _short_group(name: str) -> str:
    cleaned = re.sub(r"\s*models\s*$", "", name.strip(), flags=re.I)
    return "Claude/GPT" if re.fullmatch(r"claude and gpt", cleaned, re.I) else cleaned


def _short_limit(name: str) -> str:
    lowered = name.lower()
    if "five hour" in lowered or "5 hour" in lowered:
        return "5h"
    if "weekly" in lowered or "week" in lowered:
        return "Weekly"
    if "daily" in lowered:
        return "Daily"
    return re.sub(r"\s*limit\s*remaining\s*$", "", name.strip(), flags=re.I) or "Quota"


def parse_usage(text: str) -> list[Meter]:
    """Rows of: group, limit name, remaining percentage, reset timestamp."""
    meters: list[Meter] = []
    for line in text.splitlines():
        fields = [f.strip() for f in line.split("\t") if f.strip()]
        if len(fields) < 3:
            continue
        match = _PCT.match(fields[2])
        if not match:
            continue
        remaining_pct = float(match.group(1))
        label = f"{_short_group(fields[0])} {_short_limit(fields[1])}".strip()
        meters.append(Meter(
            kind=WINDOW,
            label=label,
            # The CLI reports what is LEFT; everything else here reports what
            # has been USED.
            used_pct=round(max(0.0, 100.0 - remaining_pct), 1),
            resets_at=iso_to_epoch(fields[3]) if len(fields) > 3 else None,
        ))
    return meters


@register
class Antigravity(Provider):
    id = "antigravity"
    label = "Antigravity"
    source = "cli"

    def poll(self, settings: dict[str, Any]) -> Reading:
        label = settings.get("label", self.label)
        binary = settings.get("cli") or CLI
        if not shutil.which(binary):
            return error_reading(self.id, label, f"{binary} not on PATH",
                                 status=AUTH_NEEDED, url=settings.get("url"))
        try:
            proc = subprocess.run([binary, *USAGE_ARGS], capture_output=True, text=True,
                                  timeout=int(settings.get("timeout", 90)))
        except subprocess.TimeoutExpired:
            return error_reading(self.id, label, "`agy /usage` timed out",
                                 url=settings.get("url"))
        except OSError as exc:
            return error_reading(self.id, label, type(exc).__name__, url=settings.get("url"))
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            return error_reading(self.id, label,
                                 tail[-1][:120] if tail else "`agy /usage` failed",
                                 status=AUTH_NEEDED, url=settings.get("url"))
        meters = parse_usage(proc.stdout or "")
        if not meters:
            return error_reading(self.id, label, "no quota rows in `agy /usage` output",
                                 url=settings.get("url"))
        return Reading(id=self.id, label=label, status=OK, source=self.source,
                       fetched_at=int(time.time()), meters=meters,
                       url=settings.get("url"))
