from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from app_config import *
from medical_parser_sanitize import sanitize_diagnosis


def _format_preview_lazy(data) -> str:
    from medical_preview import format_preview
    return format_preview(data)


class ActionsNavigationMixin:
    def reparse_navigation(self, *, silent: bool = False) -> None:
        path = self.navigation_path_var.get().strip()
        if not path:
            if not silent:
                messagebox.showwarning("Нет файла", "Сначала выберите первичный документ.")
            return
        try:
            data = self._parse_primary_document(path)
            if self.primary_document_type_var.get() == "hospitalization_referral":
                data.input_document_kind = "направление на госпитализацию"
                if self.assigned_treatment_var.get().strip():
                    data.treatment_plan = self.assigned_treatment_var.get().strip()
            elif self.primary_document_type_var.get() == "primary_exam":
                data.input_document_kind = "первичный осмотр"
                if self.assigned_treatment_var.get().strip():
                    data.treatment_plan = self.assigned_treatment_var.get().strip()
                if self.case_number_var.get().strip():
                    data.case_number = self.case_number_var.get().strip()
            if self.case_number_var.get().strip():
                data.case_number = self.case_number_var.get().strip()
            if self.epi_path_var.get().strip() and Path(self.epi_path_var.get().strip()).exists():
                data.epi_text = self.service.load_epi_text(self.epi_path_var.get().strip())
            popup_discharge = self._popup_discharge_date_override.strip()
            ui_discharge = self.discharge_date_var.get().strip()
            data.discharge_date = popup_discharge or ui_discharge
            if popup_discharge and self.discharge_date_var.get().strip() != popup_discharge:
                self._set_ui_var(self.discharge_date_var, popup_discharge)
            popup_diag = self._popup_diagnosis_override.strip() or self.diagnosis_var.get().strip()
            if popup_diag and (self._popup_diagnosis_override.strip() or self._manual_diagnosis):
                data.diagnosis = sanitize_diagnosis(popup_diag)
            # Дата поступления берётся только из заголовка документа. Если
            # общий парсер где-то нашёл дату рождения, заголовочная дата
            # имеет приоритет.
            from medical_docx_title_finder import extract_admission_date_from_title_docx
            title_date = extract_admission_date_from_title_docx(path)
            # Заголовочная дата имеет приоритет, но если её нет, сохраняем
            # строгий fallback из полного разбора первичного документа. Главное —
            # не подменять дату поступления датой рождения из демографического блока.
            if title_date:
                data.admission_date = title_date
            self.data = data
            self._apply_primary_work_defaults(data)
            # ФИО из первичного документа подтягивается в UI только как имя файлов.
            # Ручная правка этого UI-поля НЕ подменяет ФИО внутри документов.
            if data.fio and (not self._manual_patient_name or not self.patient_name_var.get().strip()):
                self._set_ui_var(self.patient_name_var, data.fio)
            if data.admission_date and (not self._manual_admission_date or not self.admission_date_var.get().strip()):
                self._set_ui_var(self.admission_date_var, data.admission_date)
            if data.case_number and not self.case_number_var.get().strip():
                self.case_number_var.set(data.case_number)
            if data.diagnosis and (not self._manual_diagnosis or not self.diagnosis_var.get().strip()):
                self._set_ui_var(self.diagnosis_var, data.diagnosis)
            # Если папки уже известны, автоматически подставляем:
            # 1) текст дневников по названию диагноза;
            # 2) конкретный 01–31 DOCX-шаблон по дате госпитализации.
            self._auto_select_diary_text_by_diagnosis(ask_folder=False)
            self._auto_select_numbered_diary_template(ask_folder=False)
            self._set_preview(_format_preview_lazy(data))
            self._log(f"\n✅ Первичный документ прочитан ({data.input_document_kind or 'тип не определён'}). Данные подтянуты в общую карточку пациента.\n")
        except Exception as exc:
            self._show_error("Не удалось прочитать первичный документ", exc)
