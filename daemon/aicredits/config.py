"""Config file at ~/.config/aicredits/config.toml.

Single source of truth for both the daemon and the plasmoid: the applet's
config page writes through `aicredits config set <dotted.key> <value>` rather
than touching the file, since QML has no sane way to write one.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "aicredits"
CONFIG_PATH = CONFIG_DIR / "config.toml"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "aicredits"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "aicredits"
STATE_PATH = STATE_DIR / "state.json"
DB_PATH = DATA_DIR / "history.db"

# id -> (label, dashboard url, default poll interval in seconds)
# The user timer fires every 2 minutes. HTTP and local-file adapters are cheap
# enough to run on every tick so the panel ages stay comparable. CLI adapters
# (Alibaba, Antigravity) finish in a few seconds and use the same cadence.
PROVIDER_DEFAULTS: dict[str, tuple[str, str, int]] = {
    "codex":       ("Codex",        "https://chatgpt.com/codex/settings/usage",   120),
    "grok":        ("SuperGrok",    "https://grok.com/supergrok",                 120),
    "zai":         ("ZCode GLM",    "https://z.ai/manage-apikey/apikey-list",     120),
    "claude":      ("Claude",       "https://claude.ai/settings/usage",           120),
    "alibaba":     ("Alibaba",      "https://bailian.console.aliyun.com/",        120),
    "openrouter":  ("OpenRouter",   "https://openrouter.ai/credits",              120),
    "nous":        ("Nous Portal",  "https://portal.nousresearch.com/billing",    120),
    "antigravity": ("Antigravity",  "https://antigravity.google/",                120),
}

# Fetch-path defaults. Adapters treat a missing key as these values; they are
# listed here so `aicredits config get providers` and the settings panel agree.
PROVIDER_FETCH_DEFAULTS: dict[str, dict[str, Any]] = {
    "codex": {"source": "auto", "show_extra": True},
    "grok": {"source": "auto"},
    "claude": {"show_extra": True},
    "openrouter": {"fetch_key": True},
}

DEFAULTS: dict[str, Any] = {
    "general": {
        "warn_pct": 80.0,
        "critical_pct": 95.0,
        "notify": True,
        # A provider whose data is older than this is shown as stale.
        "stale_after": 21600,
        "spark_points": 24,
    },
    "providers": {
        pid: {"enabled": True, "interval": interval, "label": label, "url": url,
              **PROVIDER_FETCH_DEFAULTS.get(pid, {})}
        for pid, (label, url, interval) in PROVIDER_DEFAULTS.items()
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as fh:
            return _merge(DEFAULTS, tomllib.load(fh))
    return _merge(DEFAULTS, {})


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _emit(data: dict, prefix: str = "") -> list[str]:
    lines: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    if scalars and prefix:
        lines.append(f"[{prefix}]")
    for key, value in scalars.items():
        lines.append(f"{key} = {_fmt(value)}")
    if scalars:
        lines.append("")
    for key, value in tables.items():
        lines.extend(_emit(value, f"{prefix}.{key}" if prefix else key))
    return lines


def save(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    header = "# aicredits configuration. Edit by hand or via `aicredits config set k.v value`.\n\n"
    tmp = CONFIG_PATH.with_suffix(".toml.tmp")
    tmp.write_text(header + "\n".join(_emit(data)).rstrip() + "\n")
    os.replace(tmp, CONFIG_PATH)


def _coerce(text: str) -> Any:
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def get(dotted: str) -> Any:
    node: Any = load()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def set_value(dotted: str, raw: str) -> Any:
    """Set a dotted key, writing only the delta against defaults to disk."""
    stored: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as fh:
            stored = tomllib.load(fh)
    node = stored
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise SystemExit(f"cannot set {dotted}: {part} is not a table")
    value = _coerce(raw)
    node[parts[-1]] = value
    save(stored)
    return value


def unset_value(dotted: str) -> bool:
    """Remove a configured override, pruning any empty parent tables."""
    if not CONFIG_PATH.exists():
        return False
    with CONFIG_PATH.open("rb") as fh:
        stored: dict[str, Any] = tomllib.load(fh)
    parts = dotted.split(".")
    node: Any = stored
    parents: list[tuple[dict[str, Any], str]] = []
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return False
        parents.append((node, part))
        node = node[part]
    if not isinstance(node, dict) or parts[-1] not in node:
        return False
    del node[parts[-1]]
    for parent, key in reversed(parents):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]
        else:
            break
    save(stored)
    return True


def enabled_providers(cfg: dict[str, Any]) -> list[str]:
    return [pid for pid, p in cfg["providers"].items() if p.get("enabled", True)]
