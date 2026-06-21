from __future__ import annotations

import traceback
import tkinter as tk
from tkinter import messagebox

from app_config import *


class ActionsUiStateMixin:
    def _mark_manual_field(self, field: str) -> None:
        if self._suspend_user_edit_tracking:
            return
        if field == "patient_name":
            self._manual_patient_name = True
        elif field == "admission_date":
            self._manual_admission_date = True
        elif field == "discharge_date":
            self._manual_discharge_date = True
        elif field == "diagnosis":
            self._manual_diagnosis = True

    def _set_ui_var(self, variable: tk.StringVar, value: str) -> None:
        self._suspend_user_edit_tracking = True
        try:
            variable.set(value)
        finally:
            self._suspend_user_edit_tracking = False

    def _set_preview(self, text: str) -> None:
        self._last_preview_text = text

    def _log(self, text: str) -> None:
        self._log_buffer.append(text)
        if hasattr(self, "status_label"):
            # В UI оставляем только короткий статус, без отдельного окна журнала.
            clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
            if clean_lines:
                self.status_label.config(text=clean_lines[-1][:180])

    def _set_status(self, text: str) -> None:
        if hasattr(self, "status_label"):
            self.status_label.config(text=text)

    def _start_progress(self) -> None:
        # Важно: не размещаем progressbar через grid во время сохранения.
        # Раньше он добавлялся в сетку action-блока и на несколько секунд
        # перерасчитывал layout, из-за чего нижние кнопки «сохранить»
        # визуально съезжали к центру окна. Теперь во время операции меняется
        # только курсор и нижняя строка статуса — геометрия кнопок стабильна.
        if hasattr(self, "progress"):
            try:
                self.progress.stop()
                self.progress.grid_remove()
            except Exception:
                pass
        if hasattr(self, "root"):
            self.root.configure(cursor="watch")
        if hasattr(self, "status_label"):
            self.status_label.config(text="Создаю отмеченные документы...")
        if hasattr(self, "root"):
            self.root.update_idletasks()

    def _stop_progress(self) -> None:
        if hasattr(self, "progress"):
            try:
                self.progress.stop()
                self.progress.grid_remove()
            except Exception:
                pass
        if hasattr(self, "root"):
            self.root.configure(cursor="")
        if hasattr(self, "status_label"):
            self.status_label.config(text="Готово")
        if hasattr(self, "root"):
            self.root.update_idletasks()

    def _show_error(self, title: str, exc: Exception) -> None:
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self._log(f"\n❌ {title}: {exc}\n{details}\n")
        messagebox.showerror(title, str(exc))
