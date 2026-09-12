from __future__ import annotations

import tkinter as tk

from app_config import ACCENT, ACCENT_2, ERROR, FIELD, FIELD_BORDER, PANEL, PANEL_3, TEXT
from dialog_fields_linking import attach_linked_field_mirroring
from dialog_fields_popup import DialogDiagnosisPopup


def normalize_prompt_field_values(app, rows: list[tuple[str, str]], values: list[str]) -> list[str]:
    """Normalize compact date fields at the popup submit boundary.

    This is intentionally independent of focus/key events: ``090926`` must be
    accepted when the doctor types it and immediately clicks the mouse on OK.
    """
    result = list(values)
    is_date_label = getattr(app, "_is_date_input_label", None)
    normalize_date = getattr(app, "_normalize_date_for_ui", None)
    if not callable(is_date_label) or not callable(normalize_date):
        return result
    for index, ((label, _initial), value) in enumerate(zip(rows, result)):
        if is_date_label(label) and value:
            result[index] = normalize_date(value)
    return result


def prompt_fields_dialog(
    self,
    *,
    title: str,
    rows: list[tuple[str, str]],
    width: int = 28,
    linked_groups: list[tuple[int, list[int]]] | None = None,
    choice_options: dict[str, tuple[str, ...]] | None = None,
) -> list[str] | None:
    win = tk.Toplevel(self.root)
    win.title(title)
    win.configure(bg=PANEL)
    win.resizable(False, False)
    win.transient(self.root)
    win.grab_set()

    result: list[str] | None = None
    entries: list[tk.Entry | None] = []
    entry_vars: list[tk.StringVar] = []
    entry_auto_values: list[str] = []
    choice_options = choice_options or {}
    diagnosis_popup = DialogDiagnosisPopup(win, self.root)

    body = tk.Frame(win, bg=PANEL, padx=18, pady=16)
    body.pack(fill="both", expand=True)
    tk.Label(body, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
    for idx, (label, initial) in enumerate(rows, start=1):
        options = choice_options.get(label)
        if options:
            entry = None
            var = _build_choice_row(body, idx, label, initial, options)
        else:
            entry, var = _build_field_row(self, body, idx, label, initial, width)
            if diagnosis_popup.is_diagnosis_label(label):
                diagnosis_popup.attach(entry, var)
        entries.append(entry)
        entry_vars.append(var)
        entry_auto_values.append(initial)
    body.grid_columnconfigure(1, weight=1)

    attach_linked_field_mirroring(entry_vars, entry_auto_values, linked_groups)

    error_label = tk.Label(body, text="", bg=PANEL, fg=ERROR, font=("Segoe UI", 8))
    error_label.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))
    buttons = _build_buttons_frame(body, len(rows) + 2)

    def ok() -> None:
        nonlocal result
        raw_values = [var.get().strip() for var in entry_vars]
        values = normalize_prompt_field_values(self, rows, raw_values)
        for index, (raw, normalized) in enumerate(zip(raw_values, values)):
            if normalized != raw:
                entry_vars[index].set(normalized)
        if not all(values):
            error_label.config(text="Заполните все поля.")
            return
        result = values
        diagnosis_popup.hide()
        win.destroy()

    def cancel() -> None:
        diagnosis_popup.hide()
        win.destroy()

    _build_action_buttons(buttons, ok, cancel)
    first_entry = next((entry for entry in entries if entry is not None), None)
    if first_entry is not None:
        first_entry.focus_set()
    win.bind("<Return>", lambda _event: ok())
    win.bind("<Escape>", lambda _event: cancel())
    self.root.wait_window(win)
    return result



def _build_choice_row(
    body: tk.Frame,
    idx: int,
    label: str,
    initial: str,
    options: tuple[str, ...],
) -> tk.StringVar:
    """Build mutually-exclusive checkbox choices while returning one canonical value."""
    tk.Label(body, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 8)).grid(
        row=idx, column=0, sticky="w", pady=6
    )
    selected = tk.StringVar(value=initial if initial in options else "")
    frame = tk.Frame(body, bg=PANEL)
    frame.grid(row=idx, column=1, sticky="w", padx=(12, 0), pady=6)
    flags: dict[str, tk.BooleanVar] = {}

    def choose(value: str) -> None:
        if flags[value].get():
            selected.set(value)
            for other, flag in flags.items():
                if other != value:
                    flag.set(False)
        elif selected.get() == value:
            selected.set("")

    for col, value in enumerate(options):
        flag = tk.BooleanVar(value=selected.get() == value)
        flags[value] = flag
        tk.Checkbutton(
            frame,
            text=value.capitalize(),
            variable=flag,
            command=lambda v=value: choose(v),
            bg=PANEL,
            fg=TEXT,
            activebackground=PANEL,
            activeforeground=TEXT,
            selectcolor=FIELD,
            relief="flat",
            padx=4,
            pady=2,
        ).grid(row=0, column=col, sticky="w", padx=(0, 14))
    return selected

def _build_field_row(
    app,
    body: tk.Frame,
    idx: int,
    label: str,
    initial: str,
    width: int,
) -> tuple[tk.Entry, tk.StringVar]:
    tk.Label(body, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 8)).grid(
        row=idx, column=0, sticky="w", pady=6
    )
    var = tk.StringVar(value=initial)
    entry = tk.Entry(
        body,
        textvariable=var,
        bg=FIELD,
        fg=TEXT,
        insertbackground=TEXT,
        relief="flat",
        width=width,
        font=("Segoe UI", 8),
        highlightbackground=FIELD_BORDER,
        highlightcolor=ACCENT,
        highlightthickness=1,
    )
    entry.grid(row=idx, column=1, sticky="ew", padx=(12, 0), ipady=6, pady=6)
    entry.bind("<Control-KeyPress>", app._entry_control_shortcut, add="+")
    bind_date = getattr(app, "_bind_date_entry_normalization", None)
    if callable(bind_date):
        bind_date(entry, var, label)
    return entry, var


def _build_buttons_frame(body: tk.Frame, row: int) -> tk.Frame:
    buttons = tk.Frame(body, bg=PANEL)
    buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    buttons.grid_columnconfigure(0, weight=1)
    return buttons


def _build_action_buttons(buttons: tk.Frame, ok, cancel) -> None:
    tk.Button(
        buttons,
        text="ОК",
        command=ok,
        bg=ACCENT_2,
        fg="#03101f",
        relief="flat",
        padx=18,
        pady=8,
        font=("Segoe UI", 10, "bold"),
    ).grid(row=0, column=0, sticky="e", padx=(0, 8))
    tk.Button(
        buttons,
        text="Отмена",
        command=cancel,
        bg=PANEL_3,
        fg=TEXT,
        relief="flat",
        padx=18,
        pady=8,
        font=("Segoe UI", 8),
    ).grid(row=0, column=1, sticky="e")
