"""Windows GUI wiring smoke for the real Tk application.

This check intentionally instantiates the production CombinedMedicalDiaryApp,
uses real Tk widgets/TkDND, and drives a couple of user-facing controls through
mouse events. Heavy document correctness remains covered by the DOCX smoke
suite; this file closes the UI-wiring gap between headless method tests and the
packaged EXE startup probe.
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

import files_mixin
from app import CombinedMedicalDiaryApp
from startup import _create_root


def _click(root, widget) -> None:
    # Keep press/release contiguous. Pumping Tk's idle queue between them can
    # synthesize a <Leave> from the runner's real mouse position, which resets
    # the production button's pressed state before ButtonRelease arrives.
    root.update_idletasks()
    widget.event_generate("<Enter>")
    widget.event_generate("<ButtonPress-1>", x=8, y=8)
    widget.event_generate("<ButtonRelease-1>", x=8, y=8)
    root.update_idletasks()


def main() -> None:
    if os.name != "nt":
        print("GUI RUNTIME CHECK SKIPPED: Windows-only")
        return

    with TemporaryDirectory(prefix="medical-autofill-gui-") as temp_dir:
        temp_root = Path(temp_dir)
        os.environ["APPDATA"] = str(temp_root / "appdata")

        dates_dir = temp_root / "Даты"
        dates_dir.mkdir()
        Document().save(dates_dir / "01.docx")

        root = _create_root(require_dnd=True)
        original_askdirectory = files_mixin.filedialog.askdirectory
        try:
            app = CombinedMedicalDiaryApp(root)
            # Mouse events on custom Canvas buttons are meaningful only after the
            # real top-level and its descendants are mapped. A withdrawn window
            # can still accept direct bindings (the drop-zone) while discarding
            # stateful press/release button semantics.
            root.update_idletasks()
            root.deiconify()
            root.update()

            assert app._register_tkinterdnd_drop_targets(), "TkDND targets did not register"
            assert hasattr(app, "drop_zone"), "Primary drop zone missing"
            assert hasattr(app, "diary_dates_button"), "Dates button missing"
            assert app.drop_zone.winfo_ismapped(), "Primary drop-zone is not mapped"
            assert app.diary_dates_button.winfo_ismapped(), "Dates button is not mapped"

            # Drive the actual visible primary drop-zone. Its click binding must
            # call the production navigation chooser; dormant compatibility
            # controls are not treated as part of the current user path.
            navigation_clicks: list[str] = []
            app.choose_navigation = lambda: navigation_clicks.append("choose_navigation")
            _click(root, app.drop_zone)
            assert navigation_clicks == ["choose_navigation"], "Primary drop-zone click is not wired"

            # User clicks «Даты»: exactly one folder dialog is used and the
            # numbered template is selected from that folder.
            app.admission_date_var.set("01.01.2026")
            calls: list[str] = []

            def choose_dates_folder(*_args, **_kwargs):
                calls.append("askdirectory")
                return str(dates_dir)

            files_mixin.filedialog.askdirectory = choose_dates_folder
            _click(root, app.diary_dates_button)
            assert calls == ["askdirectory"], f"Unexpected Dates-dialog flow: {calls!r}"
            assert Path(app.diary_template_dir) == dates_dir
            assert app.diary_files and Path(app.diary_files[0]).name == "01.docx"

            print("GUI RUNTIME CHECK OK")
        finally:
            files_mixin.filedialog.askdirectory = original_askdirectory
            try:
                root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    main()
