"""Entry point for MedicalDiaryAutofill.

The large Tkinter controller is intentionally split into focused modules:
configuration, reusable UI components, settings persistence, dialogs, file input,
numbered diary-template discovery, drag-and-drop, and creation actions.
``main.py`` stays small so the executable entry point remains stable.
"""

from __future__ import annotations

import os
import traceback
from pathlib import Path
from tkinter import messagebox

from app import CombinedMedicalDiaryApp
from app_config import (
    APP_TITLE,
    APP_VERSION,
    DIARY_KIND,
    DIARY_LABEL,
    DIR_OUTPUT,
    DIR_PRIMARY_DOCUMENTS,
    DIR_EPI,
    DIR_DIARY_TEXTS,
    DIR_DIARY_TEMPLATES,
    DIR_NUMBERED_DIARY_TEMPLATES,
)
from startup import _create_root, _startup_log_path, _write_startup_error


def _startup_probe_result_path() -> Path | None:
    value = os.environ.get("MEDICAL_AUTOFILL_STARTUP_PROBE_RESULT", "").strip()
    return Path(value) if value else None


def _write_startup_probe_result(text: str) -> None:
    path = _startup_probe_result_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run_startup_probe() -> None:
    """Exercise the packaged GUI/TkDND runtime and exit without user interaction."""
    root = _create_root(require_dnd=True)
    try:
        root.withdraw()
        app = CombinedMedicalDiaryApp(root)
        root.update_idletasks()
        root.update()
        if not app._register_tkinterdnd_drop_targets():
            raise RuntimeError("TkDND loaded but production drop targets could not be registered")
        required_widgets = ("drop_zone", "status_files_button", "diary_dates_button", "progress")
        missing = [name for name in required_widgets if not hasattr(app, name)]
        if missing:
            raise RuntimeError("GUI startup probe misses widgets: " + ", ".join(missing))
        _write_startup_probe_result(f"OK\nversion={APP_VERSION}\ndnd=1\n")
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def main() -> None:
    probe_mode = os.environ.get("MEDICAL_AUTOFILL_STARTUP_PROBE", "").strip() == "1"
    try:
        if probe_mode:
            _run_startup_probe()
            return
        root = _create_root()
        CombinedMedicalDiaryApp(root)
        root.mainloop()
    except Exception as exc:  # pragma: no cover - safety net for Windows double-click start
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _write_startup_error(details)
        if probe_mode:
            _write_startup_probe_result("FAIL\n" + details)
        else:
            try:
                messagebox.showerror(
                    "Ошибка запуска",
                    f"Программа не запустилась. Подробности записаны в файл:\n{_startup_log_path()}\n\n{exc}",
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
