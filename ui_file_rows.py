from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_config import *


class UiFileRowsMixin:
    def _file_row(self, parent, row: int, label: str, variable: tk.StringVar, command, button_text: str, *, optional: bool = False) -> None:
        row_pady = self._px(2 if self._compact_ui else 5, 1)
        field_height = self._px(36 if self._compact_ui else 40, 26)
        ttk.Label(parent, text=label, style="Card.TLabel", font=self._font(11)).grid(row=row, column=0, sticky="w", pady=row_pady)
        self._rounded_entry_canvas(parent, variable, height=field_height, calendar=False, font=self._font(11)).grid(
            row=row, column=1, sticky="ew", padx=(self._px(16, 9), self._px(14, 8)), pady=row_pady
        )
        self._small_neon_button(parent, text=button_text, command=command).grid(row=row, column=2, sticky="ew", pady=row_pady)
