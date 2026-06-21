from __future__ import annotations

import traceback
from pathlib import Path
import tkinter as tk

from app_config import APP_TITLE

def _startup_log_path() -> Path:
    try:
        return Path(__file__).resolve().parent / "startup_error.log"
    except Exception:
        return Path.cwd() / "startup_error.log"

def _write_startup_error(details: str) -> None:
    try:
        _startup_log_path().write_text(details, encoding="utf-8")
    except Exception:
        pass

def _create_root():
    """Создать root без падения, даже если drag/drop-библиотека не установлена."""
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore
        return TkinterDnD.Tk()
    except Exception:
        return tk.Tk()

