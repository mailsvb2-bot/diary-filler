from __future__ import annotations

from pathlib import Path

from app_config import *
from medical_constants import DOCUMENT_ORDER
from medical_models import PatientData, normalize_yes_no, parse_sick_leave_value


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

        # FIRST resolve the diary text from the visible/frozen diagnosis. The
        # doctor's folder contains hundreds of Word files named by diagnosis
        # words; it is NOT a 01–31 date-template folder. Therefore generation
        # must never start by searching that folder for day numbers.
        if not self.status_files or getattr(self, "_diary_text_files_auto_selected", False):
            self._auto_select_diary_text_by_diagnosis(
                ask_folder=False,
                diagnosis_override=(
                    patient_data_snapshot.diagnosis if patient_data_snapshot is not None else None
                ),
            )
        if not self.status_files:
            diagnosis_for_fallback = (
                patient_data_snapshot.diagnosis
                if patient_data_snapshot is not None
                else self.diagnosis_var.get().strip()
            )
            self._offer_manual_diary_text_file(
                diagnosis=diagnosis_for_fallback,
                initial_dir=getattr(self, "diary_texts_dir", "") or None,
            )
        if not self.status_files:
            raise ValueError(
                "Тексты дневников не выбраны. Остальные документы можно создать без дневников; "
                "для дневников выберите Word-файл .doc, .docx или .docm вручную."
            )

        # Numbered «Даты» are OPTIONAL. Only touch that subsystem when a Dates
        # source was explicitly configured earlier. This preserves existing
        # users who really keep a separate 01–31 folder, while a diagnosis-word
        # «Тексты» folder can never trigger a numeric lookup on its own.
        explicit_dates_source = bool(
            self.diary_files or getattr(self, "diary_template_dir", "")
        )
        if explicit_dates_source and (
            not self.diary_files or getattr(self, "_diary_files_auto_selected", False)
        ):
            self._auto_select_numbered_diary_template(
                ask_folder=False,
                admission_value_override=(
                    patient_data_snapshot.admission_date if patient_data_snapshot is not None else None
                ),
            )

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
        staff_profile = self._effective_staff_profile()
        if patient_data_snapshot is not None:
            sick_leave_needed = normalize_yes_no(patient_data_snapshot.expert_sick_leave_needed)
            sick_leave_from = patient_data_snapshot.expert_sick_leave_from.strip()
            if not sick_leave_needed and patient_data_snapshot.sick_leave:
                legacy_needed, legacy_from = parse_sick_leave_value(patient_data_snapshot.sick_leave)
                sick_leave_needed = legacy_needed
                sick_leave_from = sick_leave_from or legacy_from
            diary_birth = patient_data_snapshot.birth.strip()
            diary_complaints = patient_data_snapshot.complaints.strip()
            diary_treatment = patient_data_snapshot.treatment_plan.strip()
            diary_profile_status = patient_data_snapshot.mental_status.strip()
        else:
            sick_leave_needed = normalize_yes_no(
                self.expert_sick_leave_needed_var.get()
                if getattr(self, "expert_sick_leave_needed_var", None) is not None
                else ""
            )
            sick_leave_from = (
                self.expert_sick_leave_from_var.get().strip()
                if getattr(self, "expert_sick_leave_from_var", None) is not None
                else ""
            )
            live_data = getattr(self, "data", PatientData())
            diary_birth = str(getattr(parsed_for_name, "birth", "") or live_data.birth or "").strip()
            diary_complaints = str(getattr(parsed_for_name, "complaints", "") or live_data.complaints or "").strip()
            diary_treatment = str(
                (self.assigned_treatment_var.get().strip() if getattr(self, "assigned_treatment_var", None) is not None else "")
                or getattr(parsed_for_name, "treatment_plan", "")
                or live_data.treatment_plan
                or ""
            ).strip()
            diary_profile_status = str(
                getattr(parsed_for_name, "mental_status", "") or live_data.mental_status or ""
            ).strip()
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
            doctor_name=(patient_data_snapshot.doctor if patient_data_snapshot is not None else staff_profile["doctor"]),
            department_head_name=(patient_data_snapshot.head if patient_data_snapshot is not None else staff_profile["department_head"]),
            sick_leave_dynamic_epicrisis=(sick_leave_needed == "да"),
            sick_leave_from=sick_leave_from,
            birth_date=diary_birth,
            complaints=diary_complaints,
            treatment=diary_treatment,
            profile_status=diary_profile_status,
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
