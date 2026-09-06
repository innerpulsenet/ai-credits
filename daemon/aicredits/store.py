"""SQLite history plus the atomic JSON snapshot the plasmoid reads.

Providers are polled on independent schedules, so every run rebuilds the full
snapshot from a mix of fresh readings and the last good reading cached here.
A provider whose fetch failed keeps showing its last known value, marked stale,
rather than vanishing from the list.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from . import config as cfg
from .model import BALANCE, ERROR, OK, SPEND, STALE, WINDOW

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
  ts INTEGER NOT NULL, provider TEXT NOT NULL, meter TEXT NOT NULL,
  used_pct REAL, remaining REAL, total REAL, amount_usd REAL
);
CREATE INDEX IF NOT EXISTS readings_lookup ON readings(provider, meter, ts);
CREATE TABLE IF NOT EXISTS polls (
  provider TEXT PRIMARY KEY, last_poll INTEGER, last_ok INTEGER,
  status TEXT, message TEXT, last_good TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
  provider TEXT, meter TEXT, level TEXT, window_key TEXT, ts INTEGER,
  PRIMARY KEY (provider, meter, level, window_key)
);
"""


def connect() -> sqlite3.Connection:
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def due_providers(conn: sqlite3.Connection, config: dict[str, Any],
                  now: int, force: Iterable[str] | None = None) -> list[str]:
    forced = set(force or ())
    last = {r["provider"]: r for r in conn.execute("SELECT * FROM polls")}
    due = []
    for pid in cfg.enabled_providers(config):
        interval = int(config["providers"][pid].get("interval", 900))
        row = last.get(pid)
        if row:
            cached_reading = json.loads(row["last_good"] or "{}")
            expired = any(m.get("resets_at") and m["resets_at"] <= now
                          for m in cached_reading.get("meters", [])
                          if m.get("kind") == WINDOW)
            if row["status"] != OK or expired:
                interval = min(interval, 120)
        if pid in forced or not row or now - (row["last_poll"] or 0) >= interval:
            due.append(pid)
    return due


def record(conn: sqlite3.Connection, reading, now: int) -> None:
    """Persist one reading: history rows, poll bookkeeping, last-good cache.

    OK and STALE both carry real figures and are worth caching for display;
    only OK counts as a successful fetch and only OK is written to history,
    so an aged reading re-read on every poll cannot flatten the trend line.
    """
    if reading.status in (OK, STALE):
        for meter in (reading.meters if reading.status == OK else ()):
            conn.execute(
                "INSERT INTO readings (ts, provider, meter, used_pct, remaining, total, amount_usd)"
                " VALUES (?,?,?,?,?,?,?)",
                (now, reading.id, meter.label, meter.pct(), meter.remaining,
                 meter.total, meter.amount_usd),
            )
        conn.execute(
            "INSERT INTO polls (provider, last_poll, last_ok, status, message, last_good)"
            " VALUES (?,?,?,?,?,?) ON CONFLICT(provider) DO UPDATE SET"
            " last_poll=excluded.last_poll, last_ok=COALESCE(excluded.last_ok, polls.last_ok),"
            " status=excluded.status, message=excluded.message,"
            " last_good=excluded.last_good",
            (reading.id, now, now if reading.status == OK else None, reading.status,
             reading.message, json.dumps(reading.to_json(now))),
        )
    else:
        conn.execute(
            "INSERT INTO polls (provider, last_poll, last_ok, status, message, last_good)"
            " VALUES (?,?,NULL,?,?,NULL) ON CONFLICT(provider) DO UPDATE SET"
            " last_poll=excluded.last_poll, status=excluded.status, message=excluded.message",
            (reading.id, now, reading.status, reading.message),
        )
    conn.commit()


def cached(conn: sqlite3.Connection, pid: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM polls WHERE provider = ?", (pid,)).fetchone()
    if not row or not row["last_good"]:
        return None
    data = json.loads(row["last_good"])
    data["_last_ok"] = row["last_ok"]
    data["_status"] = row["status"]
    data["_message"] = row["message"]
    return data


def spark(conn: sqlite3.Connection, pid: str, meter: str, points: int) -> list[float]:
    rows = conn.execute(
        "SELECT used_pct FROM readings WHERE provider=? AND meter=? AND used_pct IS NOT NULL"
        " ORDER BY ts DESC LIMIT ?", (pid, meter, points)).fetchall()
    return [round(r["used_pct"], 1) for r in reversed(rows)]


def prune(conn: sqlite3.Connection, keep_days: int = 90) -> None:
    conn.execute("DELETE FROM readings WHERE ts < ?", (int(time.time()) - keep_days * 86400,))
    conn.commit()


def write_snapshot(payload: dict[str, Any], path: Path | None = None) -> Path:
    path = path or cfg.STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, path)
    return path
