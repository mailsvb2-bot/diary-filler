from __future__ import annotations

import platform
import subprocess

def is_windows() -> bool:
    return platform.system().lower().startswith("win")

def _startupinfo():
    if not is_windows():
        return None
    try:
        info = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        return info
    except Exception:
        return None
