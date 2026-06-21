"""Entry point for MedicalDiaryAutofill.

The large Tkinter controller is intentionally split into focused modules:
configuration, reusable UI components, settings persistence, dialogs, file input,
numbered diary-template discovery, drag-and-drop, and creation actions.
``main.py`` stays small so the executable entry point remains stable.
"""

from __future__ import annotations

import traceback
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


def main() -> None:
    try:
        root = _create_root()
        CombinedMedicalDiaryApp(root)
        root.mainloop()
    except Exception as exc:  # pragma: no cover - safety net for Windows double-click start
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _write_startup_error(details)
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
