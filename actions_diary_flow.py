from __future__ import annotations

from app_config import *
from medical_constants import DOCUMENT_ORDER


class ActionsDiaryFlowMixin:
    def _create_diaries_impl(self):
        # Для дневников дата поступления берётся строго из заголовка
        # первичного документа/направления. Это значение затем передаётся в
        # старый fill_diary_batch как обычная строка даты; diary_filler.py не меняем.
        diary_admission_value = self._sync_admission_date_from_title(force=True)
        if self.navigation_path_var.get().strip() and not diary_admission_value:
            raise ValueError(
                "Не удалось найти дату поступления рядом с названием документа. "
                "В первичном документе должна быть строка или имя файла вида: 12.01.2026 Первичный осмотр."
            )
        if not self.diary_files or getattr(self, "_diary_files_auto_selected", False):
            self._auto_select_numbered_diary_template(ask_folder=True)
        if not self.diary_files:
            raise ValueError("Выберите папку «шаблоны дневников» через кнопку «Шаблоны дневников»/«Папка».")
        if not self.status_files:
            self._auto_select_diary_text_by_diagnosis(ask_folder=False)
        if not self.status_files:
            self.choose_status_files()
        if not self.status_files:
            raise ValueError("Выберите файл(ы) с текстами дневников. Шаблон 01–31 — это только таблица; тексты берутся из отдельного файла с дневниками.")
        diary_patient_name = self.patient_name_var.get().strip()
        source_patient_fio = ""
        if self.navigation_path_var.get().strip():
            try:
                parsed_for_name = self._parse_primary_document(self.navigation_path_var.get().strip())
                source_patient_fio = parsed_for_name.fio.strip()
                if not diary_patient_name and source_patient_fio:
                    diary_patient_name = source_patient_fio
                    self._set_ui_var(self.patient_name_var, diary_patient_name)
            except Exception:
                source_patient_fio = ""
        if not diary_patient_name:
            raise ValueError("Введите ФИО для названия файлов или выберите первичный документ с ФИО пациента.")
        if not diary_admission_value:
            diary_admission_value = self.admission_date_var.get().strip()
        if not diary_admission_value:
            raise ValueError(
                "Не удалось найти дату поступления рядом с названием документа. "
                "В первичном документе должна быть строка или имя файла вида: 12.01.2026 Первичный осмотр."
            )
        out_dir = str(self._result_output_dir())
        from diary_batch import fill_diary_batch
        result = fill_diary_batch(
            status_files=self.status_files,
            diary_files=self.diary_files,
            output_dir=out_dir,
            patient_name=diary_patient_name,
            admission_value=diary_admission_value,
            # Род дневников определяется по ФИО из первичного документа,
            # а UI-ФИО используется только для имени выходного файла.
            gender_source_name=source_patient_fio or diary_patient_name,
            discharge_value=self.discharge_date_var.get().strip(),
            repeat_statuses=self.repeat_statuses_var.get(),
            reset_each_file=self.reset_each_file_var.get(),
            keep_signature=self.keep_signature_var.get(),
            fill_months=self.fill_months_var.get(),
            force_final_diary=self.force_final_diary_var.get(),
            remove_holiday_rows=self.remove_holiday_rows_var.get(),
            open_result_folder=False,
            write_report=self._diagnostic_reports_enabled(),
        )
        self._log("\n✅ Дневники заполнены:\n")
        for path in result.created_files:
            self._log(f"- {path}\n")
        if result.report_path is not None:
            self._log(f"Отчёт: {result.report_path}\n")
        else:
            pass
        self._log(
            f"Итого: файлов {result.processed_files}, дневников {result.filled_rows}, "
            f"дат {result.month_cells_filled}, финальных записей {result.final_rows_filled}, "
            f"удалено после выписки {result.removed_after_discharge_rows}.\n"
        )
        return result

    def create_diaries(self) -> None:
        self.output_vars[DIARY_KIND].set(True)
        for kind in DOCUMENT_ORDER:
            self.output_vars[kind].set(False)
        self.create_selected_outputs()
