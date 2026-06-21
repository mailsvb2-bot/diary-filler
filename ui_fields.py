from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_config import *


class UiFieldsMixin:
    def _rounded_entry_canvas(
        self,
        parent,
        variable: tk.StringVar,
        *,
        height: int = 44,
        calendar: bool = False,
        font: tuple = ("Segoe UI", 12),
        bg_parent: str = PANEL,
    ) -> tk.Canvas:
        canvas = tk.Canvas(parent, height=height, bg=bg_parent, highlightthickness=0, bd=0)
        entry = tk.Entry(
            canvas,
            textvariable=variable,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=font,
            bd=0,
            highlightthickness=0,
        )
        entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        canvas.entry = entry  # type: ignore[attr-defined]
        entry_id = canvas.create_window(12, height // 2, anchor="w", window=entry, height=height - 12)

        def redraw(_event=None) -> None:
            width = max(80, canvas.winfo_width())
            canvas.delete("bg")
            canvas.delete("icon")
            self._gradient_round_rect(canvas, 1, 1, width - 1, height - 1, 8, "#071420", FIELD, outline=FIELD_BORDER, width=1)
            canvas.tag_lower("bg")
            entry_width = width - (48 if calendar else 24)
            canvas.coords(entry_id, 14, height // 2)
            canvas.itemconfigure(entry_id, width=max(20, entry_width), height=height - 14)
            if calendar:
                icon_scale = 0.88 if self._compact_ui else 1.0
                icon_w = 17 * icon_scale
                icon_h = 21 * icon_scale
                icon_x = width - self._px(30, 22)
                icon_y = (height - icon_h) / 2 - self._px(1, 0)
                self._draw_calendar_icon(canvas, icon_x, icon_y, color=MUTED, accent=ACCENT, scale=icon_scale)

        canvas.bind("<Configure>", redraw)
        canvas.after(1, redraw)
        return canvas

    def _rounded_label_canvas(
        self,
        parent,
        text: str,
        *,
        height: int = 36,
        fg: str = TEXT,
        font: tuple = ("Segoe UI", 9),
        bg_parent: str = PANEL,
    ) -> tuple[tk.Canvas, tk.Label]:
        canvas = tk.Canvas(parent, height=height, bg=bg_parent, highlightthickness=0, bd=0)
        label = tk.Label(canvas, text=text, bg=FIELD, fg=fg, anchor="w", font=font, padx=4)
        label_id = canvas.create_window(13, height // 2, anchor="w", window=label, height=height - 14)

        def redraw(_event=None) -> None:
            width = max(80, canvas.winfo_width())
            canvas.delete("bg")
            self._gradient_round_rect(canvas, 1, 1, width - 1, height - 1, 8, "#071420", FIELD, outline=FIELD_BORDER, width=1)
            canvas.tag_lower("bg")
            canvas.coords(label_id, 14, height // 2)
            canvas.itemconfigure(label_id, width=max(20, width - 26), height=height - 14)

        canvas.bind("<Configure>", redraw)
        canvas.after(1, redraw)
        return canvas, label

    def _field(self, parent, label: str, variable: tk.StringVar, *, row: int, col: int, colspan: int = 1, placeholder: str = "") -> None:
        """Поле ввода как на референсе: rounded-контур, тёмный фон, календарь у дат."""
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=col, columnspan=colspan, sticky="ew", padx=(0 if col == 0 else self._px(14, 8), 0), pady=(0, self._px(3, 1)))
        box.grid_columnconfigure(0, weight=1)
        ttk.Label(box, text=label, style="Card.TLabel", font=self._font(11)).grid(row=0, column=0, sticky="w")
        is_date = any(word in label.lower() for word in ("дата", "месяц", "год"))
        entry_canvas = self._rounded_entry_canvas(box, variable, height=self._px(48, 28), calendar=is_date, font=self._font(13))
        entry_canvas.grid(row=1, column=0, sticky="ew", pady=(self._px(4, 1), 0))
        if variable is getattr(self, "discharge_date_var", None):
            entry_canvas.entry.bind("<FocusOut>", self._on_discharge_date_field_commit, add="+")  # type: ignore[attr-defined]
            entry_canvas.entry.bind("<Return>", self._on_discharge_date_field_commit, add="+")  # type: ignore[attr-defined]

    def _output_folder_group(self, parent, *, row: int, col: int, colspan: int = 1) -> None:
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=col, columnspan=colspan, rowspan=2, sticky="nsew", padx=(10, 0), pady=1)
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(2, weight=0)
        ttk.Label(box, text="Папка результата", style="Card.TLabel", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        entry = tk.Entry(
            box,
            textvariable=self.output_dir_var,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI", 10),
            highlightbackground=FIELD_BORDER,
            highlightcolor=ACCENT,
            highlightthickness=1,
        )
        entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        entry.grid(row=1, column=0, sticky="ew", ipady=5, pady=(4, 0))
        tk.Frame(box, bg=BORDER_SOFT, width=2).grid(row=1, column=1, sticky="ns", padx=10, pady=(5, 0))
        self._small_neon_button(box, text="Выбрать папку", command=self.choose_output_dir).grid(
            row=1, column=2, sticky="e", pady=(5, 0)
        )

    def _diagnosis_field(self, parent, *, row: int, col: int, colspan: int = 1) -> None:
        """Ровная строка диагноза: поле и кнопка МКБ стоят на одной линии."""
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=col, columnspan=colspan, sticky="ew", pady=(0, 0))
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(1, weight=0, minsize=self._px(154, 124))

        tk.Label(box, text="Диагноз", bg=PANEL, fg=TEXT, font=self._font(11), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, self._px(3, 1))
        )

        row_frame = tk.Frame(box, bg=PANEL)
        row_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        row_frame.grid_columnconfigure(0, weight=1)
        row_frame.grid_columnconfigure(1, weight=0, minsize=self._px(154, 124))

        diagnosis_canvas = self._rounded_entry_canvas(
            row_frame,
            self.diagnosis_var,
            height=self._px(40 if self._compact_ui else 46, 28),
            calendar=False,
            font=self._font(12 if self._compact_ui else 13),
        )
        diagnosis_canvas.grid(row=0, column=0, sticky="ew", padx=(0, self._px(10, 6)), pady=0)
        self.diagnosis_entry = diagnosis_canvas.entry  # type: ignore[attr-defined]
        self.diagnosis_combo = self.diagnosis_entry
        self.diagnosis_entry.bind("<KeyRelease>", self._on_diagnosis_key_release)
        self.diagnosis_entry.bind("<Return>", self._select_first_diagnosis_match)
        self.diagnosis_entry.bind("<Down>", self._focus_diagnosis_popup)
        self.diagnosis_entry.bind("<Escape>", lambda _event: self._hide_diagnosis_popup())
        self.diagnosis_entry.bind("<FocusOut>", self._schedule_hide_diagnosis_popup)

        self._small_neon_button(row_frame, text="МКБ-10", command=self._open_diagnosis_selector).grid(
            row=0, column=1, sticky="ew", pady=0
        )

    def _sick_leave_need_field(self, parent, *, row: int, col: int, colspan: int = 1) -> None:
        """Пункт модуля 01: нужен ли больничный лист."""
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=col, columnspan=colspan, sticky="ew", padx=(self._px(14, 8), 0), pady=(0, 0))
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(1, weight=1)

        tk.Label(box, text="Нужен больничный лист?", bg=PANEL, fg=TEXT, font=self._font(11), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, self._px(3, 1))
        )

        row_frame = tk.Frame(box, bg=PANEL)
        row_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        row_frame.grid_columnconfigure(0, weight=1)
        row_frame.grid_columnconfigure(1, weight=1)

        self.expert_sick_leave_no_button = self._small_neon_button(
            row_frame,
            text="Нет",
            command=self._set_expert_sick_leave_no,
            selected=lambda: (self._normalize_yes_no(self.expert_sick_leave_needed_var.get()) or "нет") == "нет",
        )
        self.expert_sick_leave_no_button.grid(row=0, column=0, sticky="ew", padx=(0, self._px(5, 3)))

        self.expert_sick_leave_yes_button = self._small_neon_button(
            row_frame,
            text="Да",
            command=self._on_expert_sick_leave_fill,
            selected=lambda: self._normalize_yes_no(self.expert_sick_leave_needed_var.get()) == "да",
        )
        self.expert_sick_leave_yes_button.grid(row=0, column=1, sticky="ew", padx=(self._px(5, 3), 0))
        self._update_expert_sick_leave_display()

    def _set_expert_sick_leave_no(self) -> None:
        """Сбросить больничный лист в состояние по умолчанию.

        Отдельной кнопки «Нет» больше нет, но метод оставлен для внутреннего
        сброса при старте/очистке и для совместимости с прежними тестами.
        """
        self.expert_sick_leave_needed_var.set("нет")
        self.expert_sick_leave_from_var.set("")
        self.expert_sick_leave_number_var.set("")
        self._update_expert_sick_leave_display()

    def _on_expert_sick_leave_fill(self) -> None:
        """Открыть popup и после успешного ввода выбрать «да»."""
        previous = (
            self.expert_work_status_var.get(),
            self.expert_work_org_var.get(),
            self.expert_position_var.get(),
            self.expert_sick_leave_needed_var.get(),
            self.expert_sick_leave_from_var.get(),
            self.expert_sick_leave_number_var.get(),
        )
        # Popup открывается только по кнопке «Заполнить». Сам факт успешного
        # заполнения означает, что больничный лист нужен.
        self.expert_sick_leave_needed_var.set("да")
        if not self._prompt_expert_anamnesis_details(force=True):
            self.expert_work_status_var.set(previous[0])
            self.expert_work_org_var.set(previous[1])
            self.expert_position_var.set(previous[2])
            self.expert_sick_leave_needed_var.set(previous[3] or "нет")
            self.expert_sick_leave_from_var.set(previous[4])
            self.expert_sick_leave_number_var.set(previous[5] if len(previous) > 5 else "")
            if not self._normalize_yes_no(self.expert_sick_leave_needed_var.get()):
                self.expert_sick_leave_needed_var.set("нет")
        self._update_expert_sick_leave_display()

    def _on_expert_sick_leave_yes(self) -> None:
        """Совместимость со старым именем обработчика."""
        self._on_expert_sick_leave_fill()

    def _refresh_expert_sick_leave_buttons(self) -> None:
        self._update_expert_sick_leave_display()

    def _update_expert_sick_leave_display(self) -> None:
        value = self._normalize_yes_no(self.expert_sick_leave_needed_var.get()) or "нет"
        self.expert_sick_leave_display_var.set(value)
        self._redraw_selection_controls()
