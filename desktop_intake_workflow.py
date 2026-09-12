"""GUI bridge for desktop intake.

The only hand-off into the existing application is
``_apply_primary_document_path``.  This is intentional: every popup, parser,
validation rule and document-generation path remains exactly the existing
``diary-filler`` implementation.
"""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import messagebox

from desktop_intake import (
    ensure_intake_root,
    file_is_quiet,
    is_primary_document,
    prepare_patient_work_folder,
    scan_primary_candidates,
)
from desktop_intake_agent import (
    install_agent_autostart,
    start_agent_process,
    touch_gui_heartbeat,
)


_GUI_POLL_MS = 1600
_HEARTBEAT_MS = 1800


def _show_intake_error(app, text: str) -> None:
    try:
        messagebox.showerror("Выписанные пациенты", text, parent=app.root)
    except Exception:
        pass


def _process_primary(app, source_path: str | Path) -> bool:
    source = Path(source_path)
    if not source.is_file():
        return False
    if not file_is_quiet(source):
        return False
    if not is_primary_document(source):
        return False

    try:
        moved_primary = prepare_patient_work_folder(source)
        # Critical invariant: from here onward we use the application's current
        # canonical path.  No medical generation/parser logic is duplicated.
        app._apply_primary_document_path(str(moved_primary), prompt_for_referral=True)
        try:
            app.root.deiconify()
            app.root.lift()
            app.root.focus_force()
        except Exception:
            pass
        return True
    except Exception as exc:
        _show_intake_error(
            app,
            "Не удалось обработать первичный документ из папки «Выписанные пациенты».\n\n"
            f"{type(exc).__name__}: {exc}",
        )
        return False


def _schedule_heartbeat(app) -> None:
    try:
        if not app.root.winfo_exists():
            return
        touch_gui_heartbeat()
        app.root.after(_HEARTBEAT_MS, lambda: _schedule_heartbeat(app))
    except Exception:
        return


def _poll_intake(app, intake_root: Path) -> None:
    try:
        if not app.root.winfo_exists():
            return
        if not getattr(app, "_desktop_intake_processing", False):
            candidates = scan_primary_candidates(intake_root)
            if candidates:
                app._desktop_intake_processing = True
                try:
                    _process_primary(app, candidates[0])
                finally:
                    app._desktop_intake_processing = False
        app.root.after(_GUI_POLL_MS, lambda: _poll_intake(app, intake_root))
    except Exception:
        try:
            app.root.after(_GUI_POLL_MS, lambda: _poll_intake(app, intake_root))
        except Exception:
            pass


def start_gui_intake_runtime(app, *, initial_primary: str | Path | None = None) -> None:
    """Enable the patient-folder convenience layer for a normal Windows GUI."""
    if os.name != "nt" or os.environ.get("MEDICAL_AUTOFILL_DISABLE_DESKTOP_INTAKE", "").strip() == "1":
        return

    # Publish liveness before starting/updating the agent so an already open GUI
    # is never followed by a second window for the same dropped file.
    touch_gui_heartbeat()
    intake_root = ensure_intake_root()
    install_agent_autostart()
    start_agent_process()

    app._desktop_intake_processing = False
    _schedule_heartbeat(app)

    if initial_primary:
        app._desktop_intake_processing = True

        def process_initial() -> None:
            try:
                _process_primary(app, initial_primary)
            finally:
                app._desktop_intake_processing = False

        app.root.after(80, process_initial)

    app.root.after(_GUI_POLL_MS, lambda: _poll_intake(app, intake_root))
