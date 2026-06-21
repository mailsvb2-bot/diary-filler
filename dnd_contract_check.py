"""Drag-and-drop contract checks for MedicalDiaryAutofill.

This is a headless, standard-library-only check. It cannot prove that the OS
shell delivers real Windows drops, but it catches the project-level regressions
that would make the drop zone inert even when tkinterdnd2 is available.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk

from dnd_mixin import DragDropMixin

ROOT = Path(__file__).resolve().parent


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


def _fail(message: str) -> None:
    raise SystemExit(message)


class _FakeRoot:
    def __init__(self) -> None:
        self.tk = tk.Tcl()


class _DropParserProbe(DragDropMixin):
    def __init__(self) -> None:
        self.root = _FakeRoot()


def _assert_drop_parser_handles_windows_lists() -> None:
    probe = _DropParserProbe()
    cases = [
        ("{C:/Users/Пользователь/Desktop/папка с пробелом/осмотр.docx}", ["C:/Users/Пользователь/Desktop/папка с пробелом/осмотр.docx"]),
        ("{C:/a b/осмотр.docx} {D:/дневники/тексты.docx}", ["C:/a b/осмотр.docx", "D:/дневники/тексты.docx"]),
        ("C:/plain/file.docx", ["C:/plain/file.docx"]),
    ]
    for raw, expected in cases:
        parsed = probe._parse_drop_event_data(raw)
        if parsed != expected:
            _fail(f"Drop parser regression for {raw!r}: {parsed!r} != {expected!r}")


def _assert_drop_zone_is_registered_in_ui() -> None:
    layout = _read("layout_sources.py")
    required = [
        "Перетащите сюда первичный осмотр/направление на госпитализацию",
        "или нажмите здесь, чтобы выбрать файл",
        "self.drop_zone = drop",
        "self._drop_widgets = [drop, title, hint, status]",
    ]
    missing = [snippet for snippet in required if snippet not in layout]
    if missing:
        _fail("Drop-zone UI contract is incomplete: " + ", ".join(missing))


def _assert_tkinterdnd_runtime_path_exists() -> None:
    startup = _read("startup.py")
    dnd = _read("dnd_mixin.py")
    requirements = _read("requirements.txt") + "\n" + _read("requirements_build.txt")
    build = _read("build_exe_windows.bat")
    required_pairs = {
        "startup TkinterDnD root": "TkinterDnD.Tk()" in startup,
        "DND_FILES import": "from tkinterdnd2 import DND_FILES" in dnd,
        "drop_target_register call": "drop_target_register(DND_FILES)" in dnd,
        "Drop event binding": 'dnd_bind("<<Drop>>", self._on_drop_event)' in dnd,
        "drop event handler": "def _on_drop_event" in dnd and "_handle_dropped_files(paths)" in dnd,
        "tkinterdnd2 runtime dependency": "tkinterdnd2" in requirements,
        "PyInstaller tkinterdnd2 collection": "--collect-all tkinterdnd2" in build,
    }
    missing = [name for name, ok in required_pairs.items() if not ok]
    if missing:
        _fail("TkDND runtime contract is incomplete: " + ", ".join(missing))


def main() -> None:
    _assert_tkinterdnd_runtime_path_exists()
    _assert_drop_zone_is_registered_in_ui()
    _assert_drop_parser_handles_windows_lists()
    print("DND CONTRACT OK")


if __name__ == "__main__":
    main()
