"""Provider adapter contract plus shared helpers for log-parsing adapters."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterator

from ..model import Reading

# pid -> factory. Adapters register themselves at import time via @register.
REGISTRY: dict[str, Callable[[], "Provider"]] = {}


def register(cls):
    REGISTRY[cls.id] = cls
    return cls


class Provider:
    id: str = ""
    label: str = ""
    source: str = "local-log"

    def poll(self, settings: dict[str, Any]) -> Reading:
        raise NotImplementedError


def iso_to_epoch(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def tail_lines(path: Path, max_bytes: int = 4_000_000) -> Iterator[str]:
    """Yield the file's lines newest-first, reading only the trailing chunk.

    Session and log files grow to megabytes; the record we want is almost
    always near the end, so reading the whole file every two minutes is waste.
    """
    with path.open("rb") as fh:
        size = fh.seek(0, os.SEEK_END)
        start = max(0, size - max_bytes)
        fh.seek(start)
        chunk = fh.read()
    if start:                       # drop the partial first line
        chunk = chunk.split(b"\n", 1)[-1]
    for raw in reversed(chunk.split(b"\n")):
        if raw.strip():
            yield raw.decode("utf-8", "replace")


def last_json_matching(path: Path, needle: str,
                       predicate: Callable[[dict], bool] | None = None) -> dict | None:
    """Newest JSONL record containing `needle` and satisfying `predicate`."""
    for line in tail_lines(path):
        if needle not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if predicate is None or predicate(obj):
            return obj
    return None


def window_label(minutes: int | None) -> str:
    if not minutes:
        return "Usage"
    if minutes % 10080 == 0:
        weeks = minutes // 10080
        return "Weekly" if weeks == 1 else f"{weeks}-week"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return "Daily" if days == 1 else f"{days}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"
