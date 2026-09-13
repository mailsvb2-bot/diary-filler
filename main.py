"""Entry point for MedicalDiaryAutofill.

The large Tkinter controller is intentionally split into focused modules:
configuration, reusable UI components, settings persistence, dialogs, file input,
numbered diary-template discovery, drag-and-drop, and creation actions.
``main.py`` stays small so the executable entry point remains stable.
"""

from __future__ import annotations

import json
import os
import sys
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
from startup import (
    DESKTOP_INTAKE_AGENT_ARGUMENT,
    DESKTOP_INTAKE_PRIMARY_ARGUMENT,
    _create_root,
    _startup_log_path,
    _write_startup_error,
    desktop_intake_root_path,
    run_desktop_intake_agent,
    start_desktop_intake_runtime,
)

SELF_CHECK_ARGUMENT = "--self-check"


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


def _self_check_runtime_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA", "").strip() or os.environ.get("APPDATA", "").strip()
    return (Path(base) if base else Path.home() / ".medical_diary_autofill") / "MedicalDiaryAutofill"


def _self_check_settings_ok() -> tuple[bool, str]:
    base = os.environ.get("APPDATA", "").strip()
    settings = (Path(base) if base else Path.home()) / "MedicalDiaryAutofill" / "settings.json"
    if not settings.exists():
        return True, "настройки ещё не созданы"
    try:
        payload = json.loads(settings.read_text(encoding="utf-8"))
    except Exception:
        return False, "settings.json повреждён"
    if not isinstance(payload, dict):
        return False, "settings.json имеет неверный формат"
    unexpected = sorted(set(payload) - {"folders", "printer"})
    if unexpected:
        return False, "settings.json содержит неожиданные технические ключи"
    return True, "структура безопасна"


def _self_check_rows() -> list[tuple[str, bool, str]]:
    """Inspect technical installation state only; never open patient documents."""
    rows: list[tuple[str, bool, str]] = []
    rows.append(("Программа", True, f"версия {APP_VERSION}"))

    try:
        intake = desktop_intake_root_path()
        rows.append(("Выписанные пациенты", intake.is_dir(), "папка доступна" if intake.is_dir() else "папка пока не создана"))
    except Exception:
        rows.append(("Выписанные пациенты", False, "не удалось определить Desktop"))

    settings_ok, settings_message = _self_check_settings_ok()
    rows.append(("Технические настройки", settings_ok, settings_message))

    try:
        import tkinterdnd2  # noqa: F401
        rows.append(("Drag-and-drop", True, "TkDND доступен"))
    except Exception:
        rows.append(("Drag-and-drop", False, "TkDND недоступен; ручной выбор файлов остаётся рабочим"))

    runtime = _self_check_runtime_dir()
    appdata = os.environ.get("APPDATA", "").strip()
    startup_script = (
        Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "MedicalDiaryAutofill Intake.vbs"
        if appdata
        else None
    )
    startup_ok = bool(startup_script and startup_script.is_file())
    rows.append(("Фоновое наблюдение", startup_ok, "автозагрузка настроена" if startup_ok else "автозагрузка не найдена"))

    handoff = runtime / "desktop-intake-agent-handoff.json"
    handoff_ok = False
    if handoff.is_file():
        try:
            payload = json.loads(handoff.read_text(encoding="utf-8"))
            handoff_ok = (
                isinstance(payload, dict)
                and payload.get("schema") == 1
                and isinstance(payload.get("identity"), str)
                and bool(payload.get("identity"))
                and isinstance(payload.get("gui_command"), list)
                and bool(payload.get("gui_command"))
            )
        except Exception:
            handoff_ok = False
    rows.append(("Watcher handoff", handoff_ok, "состояние корректно" if handoff_ok else "состояние ещё не создано или повреждено"))

    agent_log = runtime / "desktop-intake-agent.log"
    rows.append(("Технический журнал watcher", True, "создан" if agent_log.is_file() else "пока не создан"))
    return rows


def _self_check_report() -> str:
    lines = ["ПРОВЕРКА MEDICALDIARYAUTOFILL", ""]
    for name, ok, detail in _self_check_rows():
        lines.append(f"{'✅' if ok else '⚠'} {name}: {detail}")
    lines.extend([
        "",
        "Проверка не читает медицинские документы и не меняет механику их создания.",
        "При проблеме фонового наблюдения программу по-прежнему можно использовать вручную.",
    ])
    return "\n".join(lines)


def _self_check_write_report(report: str) -> Path | None:
    try:
        runtime = _self_check_runtime_dir()
        runtime.mkdir(parents=True, exist_ok=True)
        path = runtime / "self-check.txt"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(report + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return path
    except Exception:
        return None


def _self_check_run() -> None:
    report = _self_check_report()
    path = _self_check_write_report(report)
    try:
        print(report)
    except Exception:
        pass
    try:
        suffix = f"\n\nОтчёт: {path}" if path is not None else ""
        messagebox.showinfo("Проверить программу", report + suffix)
    except Exception:
        pass


def _intake_primary_argument(argv: list[str]) -> str:
    """Read the private agent hand-off argument without changing normal CLI behavior."""
    for index, value in enumerate(argv):
        if value == DESKTOP_INTAKE_PRIMARY_ARGUMENT and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith(DESKTOP_INTAKE_PRIMARY_ARGUMENT + "="):
            return value.split("=", 1)[1]
    return ""


def main() -> None:
    probe_mode = os.environ.get("MEDICAL_AUTOFILL_STARTUP_PROBE", "").strip() == "1"
    try:
        if probe_mode:
            _run_startup_probe()
            return

        if SELF_CHECK_ARGUMENT in sys.argv[1:]:
            _self_check_run()
            return

        # The watcher is only another startup mode of the same EXE.  It never
        # creates medical documents; it only opens the normal GUI for a primary.
        if DESKTOP_INTAKE_AGENT_ARGUMENT in sys.argv[1:]:
            exit_code = run_desktop_intake_agent()
            if exit_code:
                raise SystemExit(exit_code)
            return

        root = _create_root()
        app = CombinedMedicalDiaryApp(root)

        # Hard boundary: the convenience layer ultimately hands the path to the
        # application's pre-existing _apply_primary_document_path(...) flow.
        start_desktop_intake_runtime(
            app,
            initial_primary=_intake_primary_argument(sys.argv[1:]) or None,
        )
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
