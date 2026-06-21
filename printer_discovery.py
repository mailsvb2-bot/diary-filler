from __future__ import annotations

import subprocess

from printer_platform import _startupinfo, is_windows


def list_printers() -> list[str]:
    """Return installed/local/network printer names on Windows.

    Returns an empty list on non-Windows systems or when printers cannot be
    enumerated. The UI handles that by showing a clear status.
    """
    if not is_windows():
        return []

    names: list[str] = []
    try:
        import win32print  # type: ignore

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        for printer in win32print.EnumPrinters(flags):
            # pywin32 usually returns tuples where index 2 is printer name.
            name = str(printer[2]).strip()
            if name and name not in names:
                names.append(name)
    except Exception:
        pass

    if names:
        return sorted(names, key=str.lower)

    # PowerShell fallback for environments where pywin32 is missing.
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "Get-CimInstance Win32_Printer | Sort-Object Name | Select-Object -ExpandProperty Name",
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            startupinfo=_startupinfo(),
            timeout=12,
        )
        if completed.returncode == 0:
            for line in completed.stdout.splitlines():
                name = line.strip()
                if name and name not in names:
                    names.append(name)
    except Exception:
        pass
    return sorted(names, key=str.lower)

def get_default_printer() -> str:
    if not is_windows():
        return ""
    try:
        import win32print  # type: ignore

        return str(win32print.GetDefaultPrinter()).strip()
    except Exception:
        pass
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "(Get-CimInstance Win32_Printer | Where-Object {$_.Default -eq $true} | Select-Object -First 1 -ExpandProperty Name)",
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            startupinfo=_startupinfo(),
            timeout=12,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
    except Exception:
        pass
    return ""
