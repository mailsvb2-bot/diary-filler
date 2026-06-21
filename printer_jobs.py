from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Iterable

from printer_discovery import get_default_printer
from printer_models import PrintResult
from printer_platform import _startupinfo, is_windows


def _set_default_printer(printer_name: str) -> bool:
    if not printer_name or not is_windows():
        return False
    try:
        import win32print  # type: ignore

        win32print.SetDefaultPrinter(printer_name)
        return True
    except Exception:
        pass
    try:
        # Works on older and newer Windows versions and with network printers.
        safe = printer_name.replace("'", "''")
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f"$w = New-Object -ComObject WScript.Network; $w.SetDefaultPrinter('{safe}')",
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
        return completed.returncode == 0
    except Exception:
        return False

def _print_file_with_pywin32(path: Path, printer_name: str | None) -> None:
    import win32api  # type: ignore

    verb = "printto" if printer_name else "print"
    params = f'"{printer_name}"' if printer_name else None
    rc = win32api.ShellExecute(0, verb, str(path), params, str(path.parent), 0)
    # ShellExecute returns a value > 32 on success.
    if isinstance(rc, int) and rc <= 32:
        raise RuntimeError(f"Windows ShellExecute вернул код ошибки {rc}")

def _print_file_default(path: Path) -> None:
    # os.startfile is Windows-only and delegates printing to the registered app.
    os.startfile(str(path), "print")  # type: ignore[attr-defined]

def print_files(paths: Iterable[str | Path], printer_name: str | None = None, *, delay_seconds: float = 1.4) -> PrintResult:
    """Send files to printer immediately after creation.

    ``printer_name`` is optional. If present, the helper tries to print directly
    to that printer. Returns a structured result instead of raising after the
    first failed file, so the UI can report partial success honestly.
    """
    printed: list[Path] = []
    errors: list[str] = []
    files = [Path(p) for p in paths]

    if not files:
        return PrintResult([], [])
    if not is_windows():
        return PrintResult([], ["Печать доступна только в Windows-сборке программы."])

    # Preferred path: direct print/printto via pywin32.
    try:
        import win32api  # noqa: F401  # type: ignore

        for path in files:
            try:
                if not path.exists():
                    raise FileNotFoundError(str(path))
                _print_file_with_pywin32(path, printer_name.strip() if printer_name else None)
                printed.append(path)
                time.sleep(delay_seconds)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        return PrintResult(printed, errors)
    except Exception:
        pass

    # Fallback: selected printer becomes default temporarily, then restore.
    previous_default = get_default_printer()
    selected = (printer_name or "").strip()
    switched = False
    try:
        if selected:
            switched = _set_default_printer(selected)
            if not switched:
                return PrintResult([], [f"Не удалось выбрать принтер: {selected}. Установите pywin32 или выберите принтер по умолчанию."])
        for path in files:
            try:
                if not path.exists():
                    raise FileNotFoundError(str(path))
                _print_file_default(path)
                printed.append(path)
                time.sleep(delay_seconds)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
    finally:
        if switched and previous_default and previous_default != selected:
            _set_default_printer(previous_default)
    return PrintResult(printed, errors)
