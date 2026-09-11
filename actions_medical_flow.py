from __future__ import annotations

import copy
from pathlib import Path
from typing import List
from tkinter import messagebox

from app_config import *
from medical_formatting import parse_date
from medical_parser_sanitize import sanitize_diagnosis


def _format_preview_lazy(data) -> str:
    from medical_preview import format_preview
    return format_preview(data)
from medical_models import PatientData, normalize_admission_occurrence


class ActionsMedicalFlowMixin:
    def _medical_override_data(self, navigation: str) -> PatientData:
        data = self._parse_primary_document(navigation)
        selected_source_type = self.primary_document_type_var.get()
        if selected_source_type == "hospitalization_referral":
            data.input_document_kind = "направление на госпитализацию"
            # Для направления лечение вводится вручную через UI, потому что
            # в самом направлении блока «План лечения» может не быть.
            if self.assigned_treatment_var.get().strip():
                data.treatment_plan = self.assigned_treatment_var.get().strip()
        elif selected_source_type == "primary_exam":
            data.input_document_kind = "первичный осмотр"
            if self.assigned_treatment_var.get().strip():
                data.treatment_plan = self.assigned_treatment_var.get().strip()
            if self.case_number_var.get().strip():
                data.case_number = self.case_number_var.get().strip()
        if self.case_number_var.get().strip():
            data.case_number = self.case_number_var.get().strip()
        # UI-ФИО используется только для имени создаваемых файлов.
        # ФИО внутри документов не подменяется вручную введённым названием файла.
        data.output_fio = self.patient_name_var.get().strip() or data.fio
        # Дата поступления для медицинских документов тоже сначала берётся
        # из заголовка первичного документа. UI-значение допускается только
        # как ручная замена, если оно является полной датой и заголовок не найден.
        from medical_docx_title_finder import extract_admission_date_from_title_docx
        title_date = extract_admission_date_from_title_docx(navigation)
        if title_date:
            data.admission_date = title_date
        elif self.admission_date_var.get().strip():
            value = self.admission_date_var.get().strip()
            parsed_admission = parse_date(value)
            if parsed_admission:
                data.admission_date = parsed_admission.strftime("%d.%m.%Y")
        popup_discharge = self._popup_discharge_date_override.strip()
        ui_discharge = self.discharge_date_var.get().strip()
        if popup_discharge or ui_discharge:
            data.discharge_date = popup_discharge or ui_discharge
        popup_diag = self._popup_diagnosis_override.strip()
        ui_diag = self.diagnosis_var.get().strip()
        if popup_diag:
            data.diagnosis = sanitize_diagnosis(popup_diag)
        elif ui_diag:
            data.diagnosis = sanitize_diagnosis(ui_diag)
        if self.epi_path_var.get().strip():
            data.epi_text = self.service.load_epi_text(self.epi_path_var.get().strip())
        else:
            data.epi_text = ""

        # Экспертный анамнез строго из UI/popup. Если врач заполнил эти поля,
        # они имеют приоритет над распознанными из первичного документа строками.
        shared_org, shared_position = self._shared_work_defaults()
        data.expert_work_status = self._normalize_yes_no(self.expert_work_status_var.get())
        data.expert_work_org = self.expert_work_org_var.get().strip() or shared_org
        data.expert_position = self.expert_position_var.get().strip() or shared_position
        if not data.expert_work_status and (data.expert_work_org or data.expert_position):
            data.expert_work_status = "да"
        data.expert_sick_leave_needed = self._normalize_yes_no(self.expert_sick_leave_needed_var.get())
        data.expert_sick_leave_from = self._normalize_date_for_ui(self.expert_sick_leave_from_var.get().strip())
        data.expert_sick_leave_number = self.expert_sick_leave_number_var.get().strip()
        if data.expert_work_status == "да":
            data.work_org = data.expert_work_org
            data.position = data.expert_position
        elif data.expert_work_status == "нет":
            data.work_org = "не работает"
            data.position = ""
        if data.expert_sick_leave_needed == "да":
            data.sick_leave = f"нужен с {data.expert_sick_leave_from}" if data.expert_sick_leave_from else "нужен"
        elif data.expert_sick_leave_needed == "нет":
            data.sick_leave = "не нужен"

        data.admission_occurrence = normalize_admission_occurrence(self.admission_occurrence_var.get())
        data.rvk_act_number = self.rvk_act_number_var.get().strip()
        data.rvk_military_commissariat = self.rvk_military_commissariat_var.get().strip()
        data.rvk_work_position = self.rvk_work_position_var.get().strip()
        data.vk_date = self.vk_date_var.get().strip()
        data.vk_protocol_number = self.vk_protocol_number_var.get().strip()
        data.vk_protocol_date = self.vk_protocol_date_var.get().strip()
        data.vk_mse_work_org = self.vk_mse_work_org_var.get().strip() or shared_org
        data.vk_mse_position = self.vk_mse_position_var.get().strip() or shared_position
        data.sick_leave_vk_date = self.sick_leave_vk_date_var.get().strip()
        data.sick_leave_vk_protocol_number = self.sick_leave_vk_protocol_number_var.get().strip()
        data.sick_leave_vk_protocol_date = self.sick_leave_vk_protocol_date_var.get().strip()
        data.sick_leave_vk_commission_date = self.sick_leave_vk_commission_date_var.get().strip()
        data.sick_leave_vk_work_org = self.sick_leave_vk_work_org_var.get().strip() or shared_org
        data.sick_leave_vk_position = self.sick_leave_vk_position_var.get().strip() or shared_position
        data.sick_leave_vk_work_position = self.sick_leave_vk_work_position_var.get().strip() or ", ".join(
            part for part in [data.sick_leave_vk_work_org, data.sick_leave_vk_position] if part
        )
        data.commission_date = self.commission_date_var.get().strip()
        data.commission_number = self.commission_number_var.get().strip()
        return data

    def _capture_generation_patient_data(self, *, require_primary: bool) -> PatientData:
        """Capture one canonical patient snapshot for a complete generation run.

        Medical + diary output must not independently reread live Tk fields.
        When medical documents are selected the primary document is mandatory and
        failures preserve the existing hard boundary. Diary-only compatibility
        may still work from the current card when no primary file is available.
        """
        navigation = self.navigation_path_var.get().strip()
        navigation_exists = bool(navigation and Path(navigation).exists())
        if require_primary and not navigation_exists:
            raise ValueError("Выберите первичный документ: направление на госпитализацию или первичный осмотр.")

        if require_primary:
            discharge = self.discharge_date_var.get().strip()
            if discharge and not parse_date(discharge):
                raise ValueError(
                    "Дата выписки должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, "
                    "ДДММГГГГ, ДДММГГ или коротко ДМГГ."
                )
            if discharge:
                self._set_ui_var(self.discharge_date_var, self._normalize_date_for_ui(discharge))

        if navigation_exists:
            try:
                data = self._medical_override_data(navigation)
            except Exception:
                if require_primary:
                    raise
                data = copy.deepcopy(getattr(self, "data", PatientData()))
        else:
            data = copy.deepcopy(getattr(self, "data", PatientData()))

        patient_name = self.patient_name_var.get().strip()
        if not data.fio:
            data.fio = patient_name
        data.output_fio = patient_name or data.output_fio or data.fio

        if navigation_exists:
            title_date = self._sync_admission_date_from_title(force=True)
        else:
            title_date = ""
        admission = title_date or self.admission_date_var.get().strip() or data.admission_date
        if admission:
            parsed_admission = parse_date(admission)
            data.admission_date = parsed_admission.strftime("%d.%m.%Y") if parsed_admission else admission

        discharge = (
            self._popup_discharge_date_override.strip()
            or self.discharge_date_var.get().strip()
            or data.discharge_date
        )
        if discharge:
            parsed_discharge = parse_date(discharge)
            data.discharge_date = parsed_discharge.strftime("%d.%m.%Y") if parsed_discharge else discharge

        diagnosis = (
            self._popup_diagnosis_override.strip()
            or self.diagnosis_var.get().strip()
            or data.diagnosis
        )
        if diagnosis:
            data.diagnosis = sanitize_diagnosis(diagnosis)
        return copy.deepcopy(data)

    def _create_medical_documents_impl(
        self,
        selected_docs: List[str],
        *,
        output_dir_override: Path | None = None,
        log_created: bool = True,
        patient_data_snapshot: PatientData | None = None,
    ) -> List[Path]:
        navigation = self.navigation_path_var.get().strip()
        if not navigation or not Path(navigation).exists():
            raise ValueError("Выберите первичный документ: направление на госпитализацию или первичный осмотр.")
        if patient_data_snapshot is None:
            discharge = self.discharge_date_var.get().strip()
            if discharge and not parse_date(discharge):
                raise ValueError("Дата выписки должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ.")
            if discharge:
                discharge = self._normalize_date_for_ui(discharge)
                self._set_ui_var(self.discharge_date_var, discharge)
            data = self._medical_override_data(navigation)
            epi_path = self.epi_path_var.get().strip() or None
        else:
            data = copy.deepcopy(patient_data_snapshot)
            discharge = data.discharge_date
            # EPI text is already frozen inside the canonical snapshot. Re-reading
            # the live path here would break the one-snapshot generation contract.
            epi_path = None
        out_dir = str(output_dir_override if output_dir_override is not None else self._result_output_dir())
        missing = data.missing_critical_fields()
        if missing:
            msg = "Не найдены критические поля: " + ", ".join(missing)
            if self.strict_mode_var.get():
                raise ValueError(msg + ". Проверьте, что выбран заполненный файл пациента, а не пустой шаблон.")
            if not messagebox.askyesno("Есть пропуски", msg + "\n\nПродолжить медицинские документы всё равно?"):
                raise RuntimeError("Создание медицинских документов отменено пользователем.")
        created, used_data = self.service.create_documents(
            navigation_path=navigation,
            output_dir=out_dir,
            discharge_date=discharge,
            epi_path=epi_path,
            selected_docs=selected_docs,
            override_data=data,
        )
        self._set_preview(_format_preview_lazy(used_data))
        if log_created:
            self._log("\n✅ Созданы медицинские документы:\n")
            for path in created:
                self._log(f"- {path}\n")
        return list(created)

    def create_medical_documents(self) -> None:
        selected = self.selected_medical_docs()
        if not selected:
            messagebox.showwarning("Нет документов", "Отметьте хотя бы один медицинский документ.")
            return
        self.output_vars[DIARY_KIND].set(False)
        self.create_selected_outputs()
