from __future__ import annotations

import platform
from pathlib import Path


def _os_release_values(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"').strip("'")
    return values


def parse_platform(os_release: str, proc_version: str, init: str, architecture: str) -> dict[str, object]:
    values = _os_release_values(os_release)
    return {
        "os": values.get("ID", "unknown").lower(),
        "version": values.get("VERSION_ID", "unknown"),
        "architecture": architecture,
        "wsl": "microsoft" in proc_version.lower() or "wsl" in proc_version.lower(),
        "init": init.strip() or "unknown",
    }


def collect_platform() -> dict[str, object]:
    os_release = Path("/etc/os-release").read_text(encoding="utf-8")
    proc_version = Path("/proc/version").read_text(encoding="utf-8")
    init = Path("/proc/1/comm").read_text(encoding="utf-8")
    return parse_platform(os_release, proc_version, init, platform.machine())
