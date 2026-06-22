from __future__ import annotations

import tkinter as tk

from app_config import ACCENT, BORDER, FIELD, TEXT


def _search_icd10_f(query: str, *, limit: int):
    from icd10_f import search_icd10_f as _real_search_icd10_f
    return _real_search_icd10_f(query, limit=limit)


def _format_diagnosis(item) -> str:
    from icd10_f import format_diagnosis as _real_format_diagnosis
    return _real_format_diagnosis(item)

_NAVIGATION_KEYS = {
    "Up", "Left", "Right", "Return", "Escape", "Tab",
    "Shift_L", "Shift_R", "Control_L", "Control_R",
}


class DialogDiagnosisPopup:
    def __init__(self, owner: tk.Toplevel, root: tk.Misc) -> None:
        self.owner = owner
        self.root = root
        self.popup: tk.Toplevel | None = None
        self.listbox: tk.Listbox | None = None
        self.entry: tk.Entry | None = None
        self.var: tk.StringVar | None = None

    @staticmethod
    def is_diagnosis_label(label: str) -> bool:
        return "диагноз" in (label or "").strip().lower()

    def attach(self, entry: tk.Entry, var: tk.StringVar) -> None:
        self.entry = entry
        self.var = var
        entry.bind("<KeyRelease>", self.refresh)
        entry.bind("<Down>", self.focus_popup)
        entry.bind("<Return>", self.return_if_visible)
        entry.bind("<Escape>", lambda _event: self.hide())
        entry.bind("<FocusOut>", self.schedule_hide)

    def visible(self) -> bool:
        return bool(
            self.popup is not None
            and self.popup.winfo_exists()
            and self.popup.state() == "normal"
        )

    def hide(self) -> None:
        try:
            if self.popup is not None and self.popup.winfo_exists():
                self.popup.withdraw()
        except Exception:
            pass

    def choose(self, event=None) -> str:
        if self.listbox is None:
            return "break"
        if event is not None and getattr(event, "y", None) is not None:
            index = self.listbox.nearest(event.y)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(index)
            self.listbox.activate(index)
        selection = self.listbox.curselection()
        if selection:
            self.select(self.listbox.get(selection[0]))
        return "break"

    def select(self, value: str) -> None:
        if self.var is not None:
            self.var.set(value.strip())
        if self.entry is not None:
            self.entry.icursor(tk.END)
            self.entry.focus_set()
        self.hide()

    def show(self, values: list[str], *, keep_entry_focus: bool = True) -> None:
        if not values or self.entry is None:
            self.hide()
            return
        if self.popup is None or not self.popup.winfo_exists():
            self._build_popup()
        if self.listbox is None:
            return
        self._fill_list(values)
        self._position_popup(values)
        if keep_entry_focus:
            self.owner.after_idle(lambda: self.entry.focus_set() if self.entry is not None else None)

    def refresh(self, event=None) -> None:
        if event is not None and getattr(event, "keysym", "") in _NAVIGATION_KEYS:
            return
        query = self.var.get().strip() if self.var is not None else ""
        if not query:
            self.hide()
            return
        values = [_format_diagnosis(item) for item in _search_icd10_f(query, limit=24)]
        if values:
            self.show(values, keep_entry_focus=True)
        else:
            self.hide()

    def focus_popup(self, _event=None) -> str:
        query = self.var.get().strip() if self.var is not None else ""
        if not query:
            self.hide()
            return "break"
        values = [_format_diagnosis(item) for item in _search_icd10_f(query, limit=12)]
        if values:
            self.show(values, keep_entry_focus=False)
        if self.listbox is not None:
            self.listbox.focus_set()
            if not self.listbox.curselection() and self.listbox.size():
                self.listbox.selection_set(0)
                self.listbox.activate(0)
        return "break"

    def return_if_visible(self, _event=None):
        if self.visible() and self.listbox is not None:
            return self.choose()
        return None

    def schedule_hide(self, _event=None) -> None:
        self.owner.after(180, self.hide_if_focus_left)

    def hide_if_focus_left(self) -> None:
        try:
            focus = self.owner.focus_get() or self.root.focus_get()
        except Exception:
            focus = None
        if focus in {self.entry, self.listbox}:
            return
        self.hide()

    def _build_popup(self) -> None:
        popup = tk.Toplevel(self.owner)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.configure(bg=BORDER)
        popup.transient(self.owner)
        frame = tk.Frame(popup, bg=BORDER, padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(
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
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<ButtonRelease-1>", self.choose)
        self.listbox.bind("<Return>", self.choose)
        self.listbox.bind("<Escape>", lambda _event: self.hide())
        self.listbox.bind("<FocusOut>", self.schedule_hide)
        self.popup = popup

    def _fill_list(self, values: list[str]) -> None:
        if self.listbox is None:
            return
        self.listbox.delete(0, tk.END)
        for value in values[:12]:
            self.listbox.insert(tk.END, value)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(0)
        self.listbox.activate(0)

    def _position_popup(self, values: list[str]) -> None:
        if self.popup is None or self.entry is None:
            return
        rows_count = min(6, max(1, len(values[:12])))
        width_px = max(460, self.entry.winfo_width())
        height_px = rows_count * 22 + 4
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        self.popup.geometry(f"{width_px}x{height_px}+{x}+{y}")
        self.popup.deiconify()
        self.popup.lift()
