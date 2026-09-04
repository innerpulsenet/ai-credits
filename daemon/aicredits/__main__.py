"""aicredits — collect AI subscription usage into one snapshot for the plasmoid.

  aicredits poll [--provider a,b] [--force] [--dry-run]
  aicredits status                     human-readable dump of the snapshot
  aicredits config get|set|path
  aicredits auth set|clear|list
  aicredits doctor                     what each adapter can and cannot see
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from . import config as cfg
from . import notify, renewals, secrets, store, trend
from .model import ERROR, OK, STALE, WINDOW, Reading
from .providers import REGISTRY


def _finalize(reading: Reading, general: dict[str, Any], now: int) -> Reading:
    """Apply staleness rules that no adapter should have to reimplement."""
    if reading.status != OK:
        return reading
    expired = False
    for meter in reading.meters:
        if meter.kind == WINDOW and meter.resets_at and meter.resets_at <= now:
            meter.expired = True
            expired = True
    stale_after = int(general.get("stale_after", 21600))
    age = now - reading.fetched_at if reading.fetched_at else None
    def note(text: str) -> None:
        # An adapter's own message explains *why* a figure is missing; the
        # staleness note is extra context, so keep both.
        reading.status = STALE
        reading.message = f"{reading.message}; {text}" if reading.message else text

    if expired:
        note("window has reset since this reading — run the CLI to refresh")
    elif age is not None and age > stale_after:
        note(f"data is {_age(age)} old")
    return reading


def _age(seconds: int) -> str:
    seconds = max(0, seconds)
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _enrich(entry: dict[str, Any], conn, pid: str, points: int, now: int) -> dict[str, Any]:
    """Attach sparkline and burn-rate projection from stored history."""
    primary = next((m for m in entry.get("meters", []) if m.get("used_pct") is not None), None)
    if not primary:
        return entry
    entry["spark"] = store.spark(conn, pid, primary["label"], points)
    rows = conn.execute(
        "SELECT ts, used_pct FROM readings WHERE provider=? AND meter=? AND ts > ?"
        " ORDER BY ts", (pid, primary["label"], now - 7 * 86400)).fetchall()
    projection = trend.project([(r["ts"], r["used_pct"]) for r in rows],
                               primary["used_pct"], now, primary.get("resets_at"))
    if projection:
        primary["projection"] = projection
    return entry


def cmd_poll(args) -> int:
    config = cfg.load()
    general = config["general"]
    now = int(time.time())
    conn = store.connect()

    requested = [p.strip() for p in args.provider.split(",")] if args.provider else None
    if requested:
        unknown = [p for p in requested if p not in REGISTRY]
        if unknown:
            print(f"unknown provider(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"available: {', '.join(sorted(REGISTRY))}", file=sys.stderr)
            return 2
    # --provider scopes the run; --force is what ignores the interval. With no
    # --provider, --force means every enabled provider, not none of them.
    forced = (requested or cfg.enabled_providers(config)) if args.force else None
    due = store.due_providers(conn, config, now, force=forced)
    if requested:
        due = [p for p in due if p in requested]

    fresh: dict[str, Reading] = {}
    for pid in due:
        if pid not in REGISTRY:
            continue
        settings = config["providers"][pid]
        try:
            reading = REGISTRY[pid]().poll(settings)
        except Exception as exc:                       # an adapter must never kill the run
            reading = Reading(id=pid, label=settings.get("label", pid), status=ERROR,
                              message=f"{type(exc).__name__}: {exc}", url=settings.get("url"))
        fresh[pid] = _finalize(reading, general, now)
        if not args.dry_run:
            store.record(conn, fresh[pid], now)
            notify.check(conn, fresh[pid], general, now)

    entries: list[dict[str, Any]] = []
    for pid in cfg.enabled_providers(config):
        settings = config["providers"][pid]
        if pid in fresh and fresh[pid].status in (OK, STALE):
            entry = fresh[pid].to_json(now)
        else:
            entry = _from_cache(conn, pid, settings, fresh.get(pid), now, general)
        entry = _enrich(entry, conn, pid, int(general.get("spark_points", 24)), now)
        renewal = renewals.describe(settings)
        if renewal:
            entry["renewal"] = renewal
        entries.append(entry)

    entries.sort(key=lambda e: (-(e.get("worst_pct") or -1), e["label"]))
    payload = {
        "updated_at": now,
        "providers": entries,
        "totals": _totals(entries),
    }
    if args.dry_run:
        print(json.dumps(payload, indent=1))
        return 0
    store.prune(conn)
    path = store.write_snapshot(payload)
    print(f"wrote {path} ({len(entries)} providers, {len(due)} polled)")
    return 0


def _from_cache(conn, pid: str, settings: dict[str, Any], failed: Reading | None,
                now: int, general: dict[str, Any]) -> dict[str, Any]:
    """Build an entry for a provider not freshly read this run."""
    cache = store.cached(conn, pid)
    label = settings.get("label", pid)
    if cache:
        entry = {k: v for k, v in cache.items() if not k.startswith("_")}
        last_ok = cache.get("_last_ok") or entry.get("fetched_at") or now
        entry["stale_seconds"] = max(0, now - (entry.get("fetched_at") or last_ok))
        if failed is not None and failed.status not in (OK, STALE):
            entry["status"] = STALE
            entry["message"] = failed.message
            notify.stale_alert(conn, pid, label, last_ok, now,
                               int(general.get("stale_after", 21600)) * 4)
        return entry
    if failed is not None:
        return failed.to_json(now)
    row = conn.execute("SELECT status, message FROM polls WHERE provider=?", (pid,)).fetchone()
    return {
        "id": pid, "label": label,
        "status": row["status"] if row else "never_polled",
        "message": (row["message"] if row else "not polled yet"),
        "source": "unknown", "meters": [], "url": settings.get("url"),
    }


def _totals(entries: list[dict[str, Any]]) -> dict[str, Any]:
    monthly = sum(e["renewal"]["monthly_usd"] for e in entries if e.get("renewal"))
    upcoming = sorted((e for e in entries if e.get("renewal")),
                      key=lambda e: e["renewal"]["days_until"])
    totals: dict[str, Any] = {"monthly_usd": round(monthly, 2)}
    if upcoming:
        head = upcoming[0]
        totals["next_renewal"] = {"id": head["id"], "label": head["label"], **head["renewal"]}
    worst = [e for e in entries if e.get("worst_pct") is not None and e.get("status") == OK]
    if worst:
        top = max(worst, key=lambda e: e["worst_pct"])
        totals["worst"] = {"id": top["id"], "label": top["label"], "worst_pct": top["worst_pct"]}
    totals["attention"] = [e["id"] for e in entries
                           if e.get("status") not in (OK, "manual")]
    return totals


def _human(value: float) -> str:
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= limit:
            return f"{value / limit:.1f}{suffix}"
    return f"{value:g}"


def format_meter(meter: dict[str, Any]) -> str:
    """One meter as a short phrase, whichever kind it is."""
    label = meter.get("label", "?")
    if meter.get("amount_usd") is not None:
        text = f"{label} ${meter['amount_usd']:.2f}"
        if meter.get("total"):
            text += f" ({_human(meter['total'])} {meter.get('unit', '')})".rstrip() + ""
        return text
    if meter.get("used_pct") is not None:
        text = f"{label} {meter['used_pct']:.0f}%"
        if meter.get("remaining") is not None and meter.get("total"):
            text += f" ({_human(meter['remaining'])}/{_human(meter['total'])})"
        return text
    if meter.get("remaining") is not None:
        return f"{label} {_human(meter['remaining'])} {meter.get('unit', '')}".rstrip()
    if meter.get("total") is not None:
        # A spend meter's total is what you used; a balance meter's is a grant.
        suffix = "" if meter.get("kind") == "spend" else " granted"
        return f"{label} {_human(meter['total'])} {meter.get('unit', '')}{suffix}".rstrip()
    return label


def cmd_status(args) -> int:
    if not cfg.STATE_PATH.exists():
        print("no snapshot yet — run `aicredits poll`", file=sys.stderr)
        return 1
    data = json.loads(cfg.STATE_PATH.read_text())
    now = int(time.time())
    print(f"updated {_age(now - data['updated_at'])} ago\n")
    for entry in data["providers"]:
        bits = [format_meter(meter) for meter in entry.get("meters", [])]
        line = f"  {entry['label']:<14} {entry['status']:<12} {'  '.join(bits)}"
        if entry.get("message"):
            line += f"   ({entry['message']})"
        print(line)
    print(f"\n  monthly: ${data['totals']['monthly_usd']:.2f}")
    return 0


def cmd_config(args) -> int:
    if args.action == "path":
        print(cfg.CONFIG_PATH)
    elif args.action == "get":
        print(json.dumps(cfg.get(args.key) if args.key else cfg.load(), indent=1))
    elif args.action == "set":
        print(f"{args.key} = {cfg.set_value(args.key, args.value)!r}")
    return 0


def cmd_auth(args) -> int:
    if not secrets.available():
        print("secret-tool not found", file=sys.stderr)
        return 1
    if args.action == "set":
        value = args.value
        if not value:
            # Reading a secret from a TTY must not echo it: an echoed key ends
            # up in scrollback, and from there in screenshots and logs.
            if sys.stdin.isatty():
                import getpass
                value = getpass.getpass(f"{args.account} key (input hidden): ").strip()
            else:
                value = sys.stdin.readline().strip()
        if not value:
            print("no value supplied", file=sys.stderr)
            return 1
        ok = secrets.store(args.account, value)
        print("stored" if ok else "failed to store", file=sys.stderr if not ok else sys.stdout)
        return 0 if ok else 1
    if args.action == "clear":
        return 0 if secrets.clear(args.account) else 1
    for pid in sorted(REGISTRY):
        print(f"  {pid:<12} {'set' if secrets.get(pid) else '-'}")
    return 0


def cmd_doctor(args) -> int:
    config = cfg.load()
    now = int(time.time())
    for pid in sorted(REGISTRY):
        settings = config["providers"].get(pid, {})
        try:
            reading = _finalize(REGISTRY[pid]().poll(settings), config["general"], now)
            detail = reading.message or ", ".join(
                f"{m.label}={m.pct():.0f}%" if m.pct() is not None else m.label
                for m in reading.meters)
            age = f"  age {_age(now - reading.fetched_at)}" if reading.fetched_at else ""
            print(f"  {pid:<12} {reading.status:<10} {detail}{age}")
        except Exception as exc:
            print(f"  {pid:<12} {'crash':<10} {type(exc).__name__}: {exc}")
    missing = sorted(set(cfg.PROVIDER_DEFAULTS) - set(REGISTRY))
    if missing:
        print(f"\n  not yet implemented: {', '.join(missing)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aicredits", description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="cmd", required=True)

    poll = subs.add_parser("poll", help="fetch due providers and rewrite the snapshot")
    poll.add_argument("--provider", help="comma-separated provider ids")
    poll.add_argument("--force", action="store_true", help="ignore per-provider intervals")
    poll.add_argument("--dry-run", action="store_true", help="print the snapshot, write nothing")
    poll.set_defaults(func=cmd_poll)

    subs.add_parser("status", help="print the current snapshot").set_defaults(func=cmd_status)
    subs.add_parser("doctor", help="probe every adapter").set_defaults(func=cmd_doctor)

    conf = subs.add_parser("config")
    conf.add_argument("action", choices=["get", "set", "path"])
    conf.add_argument("key", nargs="?")
    conf.add_argument("value", nargs="?")
    conf.set_defaults(func=cmd_config)

    auth = subs.add_parser("auth")
    auth.add_argument("action", choices=["set", "clear", "list"])
    auth.add_argument("account", nargs="?")
    auth.add_argument("value", nargs="?")
    auth.set_defaults(func=cmd_auth)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
