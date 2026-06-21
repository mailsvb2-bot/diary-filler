from __future__ import annotations

import tkinter as tk

from app_config import ACCENT, ACCENT_2, ERROR, FIELD, FIELD_BORDER, PANEL, PANEL_3, TEXT
from dialog_fields_linking import attach_linked_field_mirroring
from dialog_fields_popup import DialogDiagnosisPopup


def prompt_fields_dialog(
    self,
    *,
    title: str,
    rows: list[tuple[str, str]],
    width: int = 28,
    linked_groups: list[tuple[int, list[int]]] | None = None,
) -> list[str] | None:
    win = tk.Toplevel(self.root)
    win.title(title)
    win.configure(bg=PANEL)
    win.resizable(False, False)
    win.transient(self.root)
    win.grab_set()

    result: list[str] | None = None
    entries: list[tk.Entry] = []
    entry_vars: list[tk.StringVar] = []
    entry_auto_values: list[str] = []
    diagnosis_popup = DialogDiagnosisPopup(win, self.root)

    body = tk.Frame(win, bg=PANEL, padx=18, pady=16)
    body.pack(fill="both", expand=True)
    tk.Label(body, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
    for idx, (label, initial) in enumerate(rows, start=1):
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
        values = [entry.get().strip() for entry in entries]
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
    if entries:
        entries[0].focus_set()
    win.bind("<Return>", lambda _event: ok())
    win.bind("<Escape>", lambda _event: cancel())
    self.root.wait_window(win)
    return result


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
