from __future__ import annotations

import tkinter as tk

from app_config import *

def _search_icd10_f(query: str, *, limit: int):
    from icd10_f import search_icd10_f as _real_search_icd10_f
    return _real_search_icd10_f(query, limit=limit)


def _format_diagnosis(item) -> str:
    from icd10_f import format_diagnosis as _real_format_diagnosis
    return _real_format_diagnosis(item)


class DiagnosisWidgetMixin:
    def _on_diagnosis_selected(self, _event=None) -> None:
        self.diagnosis_var.set(self.diagnosis_var.get().strip())
        self._hide_diagnosis_popup()

    def _on_diagnosis_key_release(self, event=None) -> None:
        if event is not None:
            if event.keysym in {"Up", "Left", "Right", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"}:
                return
            if event.keysym == "Down":
                self._focus_diagnosis_popup(event)
                return

        query = self.diagnosis_var.get().strip()
        if not query:
            self._hide_diagnosis_popup()
            return
        display_values = [_format_diagnosis(item) for item in _search_icd10_f(query, limit=24)]
        if display_values:
            self._show_diagnosis_popup(display_values[:12], keep_entry_focus=True)
        else:
            self._hide_diagnosis_popup()

    def _select_first_diagnosis_match(self, _event=None) -> str:
        query = self.diagnosis_var.get().strip()
        if not query:
            return "break"
        matches = _search_icd10_f(query, limit=1)
        if matches:
            self._select_diagnosis_value(_format_diagnosis(matches[0]))
        return "break"

    def _select_diagnosis_value(self, value: str) -> None:
        self.diagnosis_var.set(value.strip())
        self.diagnosis_entry.icursor(tk.END)
        self._hide_diagnosis_popup()
        self.diagnosis_entry.focus_set()

    def _show_diagnosis_popup(self, values: list[str], *, keep_entry_focus: bool = True) -> None:
        if not values:
            self._hide_diagnosis_popup()
            return
        self._diagnosis_popup_matches = values

        if self._diagnosis_popup is None or not self._diagnosis_popup.winfo_exists():
            popup = tk.Toplevel(self.root)
            popup.withdraw()
            popup.overrideredirect(True)
            popup.configure(bg=BORDER)
            popup.transient(self.root)
            frame = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
            frame.pack(fill="both", expand=True)
            self._diagnosis_listbox = tk.Listbox(
                frame,
                bg=FIELD,
                fg=TEXT,
                selectbackground=ACCENT,
                selectforeground="#03101f",
                activestyle="none",
                font=("Segoe UI", 9),
                height=6,
                bd=0,
                highlightthickness=0,
                exportselection=False,
            )
            self._diagnosis_listbox.pack(fill="both", expand=True)
            self._diagnosis_listbox.bind("<ButtonRelease-1>", self._choose_diagnosis_from_popup)
            self._diagnosis_listbox.bind("<Return>", self._choose_diagnosis_from_popup)
            self._diagnosis_listbox.bind("<Escape>", lambda _event: self._hide_diagnosis_popup())
            self._diagnosis_listbox.bind("<FocusOut>", self._schedule_hide_diagnosis_popup)
            self._diagnosis_popup = popup

        if self._diagnosis_listbox is None:
            return

        self._diagnosis_listbox.delete(0, tk.END)
        for value in values:
            self._diagnosis_listbox.insert(tk.END, value)
        self._diagnosis_listbox.selection_clear(0, tk.END)
        self._diagnosis_listbox.selection_set(0)
        self._diagnosis_listbox.activate(0)

        rows = min(6, max(1, len(values)))
        row_height = 22
        width = max(460, self.diagnosis_entry.winfo_width())
        height = rows * row_height + 4
        x = self.diagnosis_entry.winfo_rootx()
        y = self.diagnosis_entry.winfo_rooty() + self.diagnosis_entry.winfo_height() + 2
        self._diagnosis_popup.geometry(f"{width}x{height}+{x}+{y}")
        self._diagnosis_popup.deiconify()
        self._diagnosis_popup.lift()

        if keep_entry_focus:
            self.root.after_idle(lambda: self.diagnosis_entry.focus_set())

    def _choose_diagnosis_from_popup(self, event=None) -> str:
        listbox = self._diagnosis_listbox
        if listbox is None:
            return "break"
        if event is not None and getattr(event, "y", None) is not None:
            index = listbox.nearest(event.y)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
        selection = listbox.curselection()
        if selection:
            self._select_diagnosis_value(listbox.get(selection[0]))
        return "break"

    def _focus_diagnosis_popup(self, _event=None) -> str:
        query = self.diagnosis_var.get().strip()
        if not query:
            self._hide_diagnosis_popup()
            return "break"
        values = [_format_diagnosis(item) for item in _search_icd10_f(query, limit=12)]
        if values:
            self._show_diagnosis_popup(values, keep_entry_focus=False)
        if self._diagnosis_listbox is not None:
            self._diagnosis_listbox.focus_set()
            if not self._diagnosis_listbox.curselection() and self._diagnosis_listbox.size():
                self._diagnosis_listbox.selection_set(0)
                self._diagnosis_listbox.activate(0)
        return "break"

    def _schedule_hide_diagnosis_popup(self, _event=None) -> None:
        self.root.after(180, self._hide_diagnosis_popup_if_focus_left)

    def _hide_diagnosis_popup_if_focus_left(self) -> None:
        focus = self.root.focus_get()
        if focus in {self.diagnosis_entry, self._diagnosis_listbox}:
            return
        self._hide_diagnosis_popup()

    def _hide_diagnosis_popup(self) -> None:
        if self._diagnosis_popup is not None and self._diagnosis_popup.winfo_exists():
            self._diagnosis_popup.withdraw()

    def _open_diagnosis_selector(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Выбор диагноза: МКБ-10, раздел F")
        win.configure(bg=PANEL)
        win.geometry("720x520")
        win.minsize(620, 440)
        win.transient(self.root)
        win.grab_set()

        body = tk.Frame(win, bg=PANEL, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        tk.Label(
            body,
            text="МКБ-10: психические расстройства и расстройства поведения, F00-F99",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            body,
            text="Введите код, цифры кода или часть названия. Например: 41, F41.2, тревож, шизо.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        search_var = tk.StringVar(value=self.diagnosis_var.get().strip())
        search_entry = tk.Entry(body, textvariable=search_var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 11), highlightbackground=FIELD_BORDER, highlightcolor=ACCENT, highlightthickness=1)
        search_entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        search_entry.grid(row=2, column=0, sticky="new", ipady=7)

        list_frame = tk.Frame(body, bg=PANEL)
        list_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)

        scrollbar = tk.Scrollbar(list_frame)
        listbox = tk.Listbox(
            list_frame,
            bg=FIELD,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground="#03101f",
            activestyle="none",
            font=("Segoe UI", 10),
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=listbox.yview)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        current_matches = []

        def refresh(*_args) -> None:
            nonlocal current_matches
            current_matches = _search_icd10_f(search_var.get(), limit=300)
            listbox.delete(0, tk.END)
            for item in current_matches:
                listbox.insert(tk.END, _format_diagnosis(item))
            if current_matches:
                listbox.selection_set(0)
                listbox.activate(0)

        def choose() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            value = listbox.get(selection[0])
            self.diagnosis_var.set(value)
            self._hide_diagnosis_popup()
            win.destroy()

        buttons = tk.Frame(body, bg=PANEL)
        buttons.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        buttons.grid_columnconfigure(0, weight=1)
        tk.Button(
            buttons,
            text="Выбрать диагноз",
            command=choose,
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
            command=win.destroy,
            bg=PANEL_3,
            fg=TEXT,
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 10),
        ).grid(row=0, column=1, sticky="e")

        search_var.trace_add("write", refresh)
        listbox.bind("<Double-Button-1>", lambda _event: choose())
        listbox.bind("<Return>", lambda _event: choose())
        search_entry.bind("<Return>", lambda _event: choose())
        win.bind("<Escape>", lambda _event: win.destroy())

        refresh()
        search_entry.focus_set()
        self.root.wait_window(win)
