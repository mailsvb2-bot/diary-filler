from __future__ import annotations

from pathlib import Path

from app_config import *
from medical_constants import DOCUMENT_ORDER
from medical_models import PatientData


class ActionsDiaryFlowMixin:
    def _create_diaries_impl(
        self,
        *,
        output_dir_override: Path | None = None,
        log_created: bool = True,
        patient_data_snapshot: PatientData | None = None,
    ):
        # Один запуск комплекта использует один frozen patient snapshot. Старый
        # прямой internal API без snapshot сохраняет прежний live-UI fallback.
        if patient_data_snapshot is None:
            diary_admission_value = self._sync_admission_date_from_title(force=True)
        else:
            diary_admission_value = patient_data_snapshot.admission_date.strip()
        if self.navigation_path_var.get().strip() and not diary_admission_value:
            raise ValueError(
                "Не удалось найти дату поступления рядом с названием документа. "
                "В первичном документе должна быть строка или имя файла вида: 12.01.2026 Первичный осмотр."
            )
        if not self.diary_files or getattr(self, "_diary_files_auto_selected", False):
            self._auto_select_numbered_diary_template(
                ask_folder=True,
                admission_value_override=(
                    patient_data_snapshot.admission_date if patient_data_snapshot is not None else None
                ),
            )
        if not self.diary_files:
            raise ValueError("Выберите папку «Даты» с шаблонами дневников 01–31.")
        if not self.status_files:
            self._auto_select_diary_text_by_diagnosis(
                ask_folder=False,
                diagnosis_override=(
                    patient_data_snapshot.diagnosis if patient_data_snapshot is not None else None
                ),
            )
        if not self.status_files:
            self.choose_status_files()
        if not self.status_files:
            raise ValueError("Выберите папку «Тексты» с DOCX по диагнозам. Источник «Даты» задаёт календарь, а тексты подбираются по диагнозу.")
        if patient_data_snapshot is None:
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
            if not diary_admission_value:
                diary_admission_value = self.admission_date_var.get().strip()
        else:
            diary_patient_name = (patient_data_snapshot.output_fio or patient_data_snapshot.fio).strip()
            source_patient_fio = patient_data_snapshot.fio.strip()
        if not diary_patient_name:
            raise ValueError("Введите ФИО для названия файлов или выберите первичный документ с ФИО пациента.")
        if not diary_admission_value:
            raise ValueError(
                "Не удалось найти дату поступления рядом с названием документа. "
                "В первичном документе должна быть строка или имя файла вида: 12.01.2026 Первичный осмотр."
            )
        out_dir = str(output_dir_override if output_dir_override is not None else self._result_output_dir())
        from diary_service import DiaryService
        result = DiaryService().create_text_diaries(
            status_files=self.status_files,
            diary_files=self.diary_files,
            output_dir=out_dir,
            patient_name=diary_patient_name,
            admission_value=diary_admission_value,
            # Род дневников определяется по ФИО из первичного документа,
            # а UI-ФИО используется только для имени выходного файла.
            gender_source_name=source_patient_fio or diary_patient_name,
            discharge_value=(
                patient_data_snapshot.discharge_date
                if patient_data_snapshot is not None
                else self.discharge_date_var.get().strip()
            ),
            repeat_statuses=self.repeat_statuses_var.get(),
            force_final_diary=self.force_final_diary_var.get(),
            write_report=self._diagnostic_reports_enabled(),
        )
        if log_created:
            self._log("\n✅ Дневники заполнены:\n")
            for path in result.created_files:
                self._log(f"- {path}\n")
            if result.report_path is not None:
                self._log(f"Отчёт: {result.report_path}\n")
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
