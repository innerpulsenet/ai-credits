"""Credentials via secret-tool (libsecret -> the running kwalletd6).

Namespaced `service=aicredits account=<provider>`. Shelling out avoids a
python-keyring dependency that isn't installed on this system, and keeps the
secret out of any file we write.
"""

from __future__ import annotations

import shutil
import subprocess
import time

SERVICE = "aicredits"


def available() -> bool:
    return shutil.which("secret-tool") is not None


def get(account: str) -> str | None:
    if not available():
        return None
    # The desktop keyring can briefly return an empty lookup during startup.
    # Bound each attempt so a locked/unavailable wallet cannot stall all panes.
    for attempt in range(2):
        try:
            proc = subprocess.run(
                ["secret-tool", "lookup", "service", SERVICE, "account", account],
                capture_output=True, text=True, timeout=5)
            value = proc.stdout.strip()
            if proc.returncode == 0 and value:
                return value
        except (OSError, subprocess.TimeoutExpired):
            pass
        if attempt == 0:
            time.sleep(0.2)
    return None


def store(account: str, value: str) -> bool:
    if not available():
        return False
    proc = subprocess.run(
        ["secret-tool", "store", "--label", f"aicredits: {account}",
         "service", SERVICE, "account", account],
        input=value, capture_output=True, text=True)
    return proc.returncode == 0


def clear(account: str) -> bool:
    if not available():
        return False
    proc = subprocess.run(["secret-tool", "clear", "service", SERVICE, "account", account],
                          capture_output=True, text=True)
    return proc.returncode == 0
