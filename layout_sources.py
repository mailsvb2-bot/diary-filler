from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from app_config import *


class LayoutSourcesMixin:
    def _drop_zone_row(self, parent: tk.Frame, row: int) -> None:
        # Совместимость: старое имя оставлено, но используется новый компактный блок.
        self._source_drop_row(parent, row)

    def _source_drop_row(self, parent: tk.Frame, row: int) -> None:
        # Drop-зона должна иметь одну и ту же высоту до и после выбора файла.
        # Иначе при появлении статуса выбранного DOCX Tk пересчитывает высоту
        # верхней строки, а нижние поля первого блока, включая кнопки «Нет/Да»,
        # визуально подпрыгивают. Поэтому внешняя геометрия зоны фиксирована,
        # а меняется только текст внутри уже зарезервированного места.
        drop_height = self._px(96 if self._compact_ui else 106, 78)
        drop = tk.Frame(
            parent,
            bg=FIELD,
            highlightbackground=FIELD_BORDER,
            highlightthickness=1,
            bd=0,
            cursor="hand2",
            height=drop_height,
        )
        drop.grid(row=row, column=0, sticky="ew", pady=(self._px(3, 1), self._px(5, 2)))
        drop.grid_propagate(False)
        drop.grid_columnconfigure(0, weight=1)
        drop.grid_rowconfigure(0, minsize=self._px(38 if self._compact_ui else 44, 28))
        # Строка 1 — единая строка сообщения: сначала подсказка, после выбора
        # файла — зелёный статус. Так текст не проваливается вниз, а высота
        # drop-зоны остаётся стабильной.
        drop.grid_rowconfigure(1, minsize=self._px(24 if self._compact_ui else 28, 18))
        drop.grid_rowconfigure(2, minsize=self._px(14 if self._compact_ui else 18, 10))

        title = tk.Label(
            drop,
            text="Перетащите сюда первичный осмотр/направление на госпитализацию",
            bg=FIELD,
            fg=TEXT,
            font=self._font(12, weight="bold"),
            padx=self._px(18, 12),
            pady=0,
        )
        title.grid(row=0, column=0, sticky="ew", pady=(self._px(15 if self._compact_ui else 18, 9), self._px(3, 1)))

        hint = tk.Label(
            drop,
            text="или нажмите здесь, чтобы выбрать файл",
            bg=FIELD,
            fg=MUTED_2,
            font=self._font(9),
            padx=self._px(18, 12),
            pady=0,
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(0, self._px(12 if self._compact_ui else 15, 7)))

        # Подсказка визуально исчезает после выбора файла, но её grid-слот
        # остаётся зарезервированным. Поэтому строка статуса не меняет высоту
        # drop-зоны и не двигает кнопки первого блока.
        self.primary_drop_hint_label = hint

        self.primary_selected_status_var = tk.StringVar(value=" ")
        status = tk.Label(
            drop,
            textvariable=self.primary_selected_status_var,
            bg=FIELD,
            fg=SUCCESS,
            font=self._font(10),
            padx=self._px(18, 12),
            pady=0,
            wraplength=self._px(760, 520),
            justify="center",
            anchor="center",
        )
        # Статус выбранного файла занимает ту же вертикальную строку, что и
        # подсказка. Подсказка становится пустой, но не снимается с grid,
        # поэтому блок 01 не прыгает, а зелёный текст выглядит выше и ровнее.
        status.grid(row=1, column=0, sticky="ew", pady=(0, self._px(10, 5)))
        for widget in (drop, title, hint, status):
            widget.bind("<Button-1>", lambda _event: self.choose_navigation())
        self.drop_zone = drop
        self.primary_selected_status_label = status
        self._drop_widgets = [drop, title, hint, status]

    def _set_primary_drop_empty(self) -> None:
        """Вернуть drop-зону в исходное компактное состояние."""
        if hasattr(self, "primary_drop_hint_label"):
            self.primary_drop_hint_label.config(text="или нажмите здесь, чтобы выбрать файл", fg=MUTED_2)
        if hasattr(self, "primary_selected_status_var"):
            self.primary_selected_status_var.set(" ")

    def _set_primary_drop_selected(self, path: str) -> None:
        """Показать выбранный первичный файл без распирания блока 01."""
        filename = Path(path).name if path else ""
        max_chars = 54 if self._compact_ui else 82
        if hasattr(self, "_truncate_label_text"):
            filename = self._truncate_label_text(filename, max_chars=max_chars)
        elif len(filename) > max_chars:
            filename = filename[: max_chars - 1].rstrip() + "…"
        kind_text = (
            "Выбрано направление"
            if self.primary_document_type_var.get() == "hospitalization_referral"
            else "Выбран первичный осмотр"
        )
        if hasattr(self, "primary_drop_hint_label"):
            # После выбора файла фраза «или нажмите здесь…» уже не нужна.
            # Но сам label не снимаем с grid: строка остаётся зарезервированной,
            # поэтому первый блок и кнопки «Нет/Да» не меняют координаты.
            self.primary_drop_hint_label.config(text="", fg=FIELD)
        if hasattr(self, "primary_selected_status_var"):
            self.primary_selected_status_var.set(f"{kind_text}: {filename}")

    def _primary_type_row(self, parent: tk.Frame, row: int) -> None:
        ttk.Label(parent, text="Тип первичного документа", style="Card.TLabel", font=self._font(11)).grid(
            row=row, column=0, sticky="w", pady=self._px(4 if self._compact_ui else 5, 2)
        )
        # Визуально это теперь такое же тёмное поле, как в референсе, без квадратной combobox-стрелки.
        self._rounded_entry_canvas(parent, self.primary_document_type_display_var, height=self._px(40, 27), calendar=False, font=self._font(12)).grid(
            row=row, column=1, sticky="ew", padx=(self._px(16, 9), self._px(14, 8)), pady=self._px(4 if self._compact_ui else 5, 2)
        )
        self._small_neon_button(parent, text="Выбрать", command=self._toggle_primary_document_type).grid(
            row=row, column=2, sticky="ew", pady=self._px(4 if self._compact_ui else 5, 2)
        )

    def _on_primary_type_display_selected(self, _event=None) -> None:
        display = self.primary_document_type_display_var.get().strip()
        self.primary_document_type_var.set("hospitalization_referral" if display.startswith("Направление") else "primary_exam")
        self._on_primary_document_type_changed()

    def _toggle_primary_document_type(self) -> None:
        current = self.primary_document_type_var.get()
        self.primary_document_type_var.set("hospitalization_referral" if current == "primary_exam" else "primary_exam")
        desired_display = "Направление на госпитализацию" if self.primary_document_type_var.get() == "hospitalization_referral" else "Первичный осмотр"
        self.primary_document_type_display_var.set(desired_display)
        self._on_primary_document_type_changed()

    def _multi_file_row(self, parent, row: int, label: str, kind: str) -> None:
        ttk.Label(parent, text=label, style="Card.TLabel", font=self._font(11)).grid(row=row, column=0, sticky="w", pady=self._px(4 if self._compact_ui else 5, 2))
        value = "Файлы не выбраны"
        if kind == "status" and self.status_files:
            value = f"Выбрано файлов: {len(self.status_files)}"
        elif kind == "diary" and self.diary_files:
            value = "Выбран: " + Path(self.diary_files[0]).name
        elif kind == "diary" and self.diary_template_dir:
            value = "Папка: " + Path(self.diary_template_dir).name
        display_canvas, display = self._rounded_label_canvas(
            parent,
            value,
            height=self._px(40, 27),
            fg=MUTED if value == "Файлы не выбраны" else TEXT,
            font=self._font(11),
        )
        display_canvas.grid(row=row, column=1, sticky="ew", padx=(self._px(16, 9), self._px(14, 8)), pady=self._px(4 if self._compact_ui else 5, 2))
        if kind == "status":
            self.status_files_label = display
            command = self.choose_status_files
        else:
            self.diary_files_label = display
            command = self.choose_diary_files
        button_text = "Папка" if kind == "diary" else "Выбрать"
        self._small_neon_button(parent, text=button_text, command=command).grid(row=row, column=2, sticky="ew", pady=self._px(4 if self._compact_ui else 5, 2))

    def _diary_compact_row(self, parent, row: int) -> None:
        """Компактный блок выбора текстов и дат дневников."""
        ttk.Label(parent, text="Дневники", style="Card.TLabel", font=self._font(11)).grid(
            row=row, column=0, sticky="w", pady=self._px(2, 1)
        )

        info = tk.Frame(parent, bg=PANEL)
        info.grid(row=row, column=1, sticky="ew", padx=(self._px(16, 9), self._px(14, 8)), pady=(0, 0))
        info.grid_columnconfigure(0, weight=1)
        self.status_files_label = tk.Label(
            info,
            text="Тексты: не выбраны",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            font=self._font(9),
        )
        self.status_files_label.grid(row=0, column=0, sticky="ew")
        self.diary_files_label = tk.Label(
            info,
            text="Даты: не выбраны",
            bg=PANEL,
            fg=MUTED,
            anchor="w",
            font=self._font(9),
        )
        self.diary_files_label.grid(row=1, column=0, sticky="ew", pady=(0, 0))

        buttons = tk.Frame(parent, bg=PANEL)
        buttons.grid(row=row, column=2, sticky="ew", pady=self._px(2, 1))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        self.status_files_button = self._small_neon_button(
            buttons,
            text="Тексты",
            command=self.choose_status_files,
            selected=lambda: bool(self.status_files),
        )
        self.status_files_button.grid(row=0, column=0, sticky="ew", padx=(0, self._px(4, 2)))
        self.diary_dates_button = self._small_neon_button(
            buttons,
            text="Даты",
            command=self.choose_diary_files,
            selected=lambda: bool(self.diary_files or getattr(self, "diary_template_dir", "")),
        )
        self.diary_dates_button.grid(row=0, column=1, sticky="ew", padx=(self._px(4, 2), 0))
