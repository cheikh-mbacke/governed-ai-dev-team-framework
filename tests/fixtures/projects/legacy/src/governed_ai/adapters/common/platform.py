"""OS/platform detection shared by every Adaptateur runtime.

No tool-specific content — pure ``sys.platform``/WSL detection, reused by
``ExecutionRequest.platform`` resolution and compatibility negotiation.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


def platform_profile() -> str:
    if sys.platform == "win32":
        return "windows-native"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        release = platform.release().lower()
        proc_version = ""
        try:
            proc_version = Path("/proc/version").read_text(
                encoding="utf-8", errors="ignore"
            ).lower()
        except OSError:
            pass
        if os.environ.get("WSL_INTEROP") or "microsoft" in release or "microsoft" in proc_version:
            return "wsl"
        return "linux"
    return sys.platform


__all__ = ["platform_profile"]
