"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List

from medical_constants import DATE_FMT

@dataclass
class PatientData:
    case_number: str = ""
    fio: str = ""
    # Имя пациента для названия создаваемых файлов.
    # ВАЖНО: это отдельное поле; оно не подменяет ФИО внутри документов.
    output_fio: str = ""
    birth: str = ""
    registered: str = ""
    psych_account: str = ""
    work_org: str = ""
    position: str = ""
    sick_leave: str = ""
    # Экспертный анамнез: заполняется из UI/popup, чтобы первичный осмотр,
    # выписной эпикриз и комиссионный осмотр писали одну согласованную формулировку.
    expert_work_status: str = ""  # да / нет
    expert_work_org: str = ""
    expert_position: str = ""
    expert_sick_leave_needed: str = ""  # да / нет
    expert_sick_leave_from: str = ""
    expert_sick_leave_number: str = ""
    disability: str = ""
    rvk_referral: str = ""
    admission: str = ""

    complaints: str = ""
    life_anamnesis: str = ""
    disease_anamnesis: str = ""
    mental_status: str = ""
    somatic_status: str = ""
    examination_plan: str = ""
    treatment_plan: str = ""
    # True only when the primary document itself contains an explicit
    # treatment section row: «Лечение», «Назначенное лечение» or
    # «План лечения». Ordinary prose like «за время лечения» is ignored.
    has_treatment_section: bool = False
    diagnosis: str = ""
    epidemiology: str = ""

    admission_date: str = ""
    discharge_date: str = ""
    epi_text: str = ""
    input_document_kind: str = ""

    # Ручные реквизиты из UI для отдельных документов.
    rvk_act_number: str = ""
    rvk_military_commissariat: str = ""
    rvk_work_position: str = ""
    vk_date: str = ""
    vk_protocol_number: str = ""
    vk_protocol_date: str = ""
    vk_mse_work_org: str = ""
    vk_mse_position: str = ""
    sick_leave_vk_date: str = ""
    sick_leave_vk_protocol_number: str = ""
    sick_leave_vk_protocol_date: str = ""
    sick_leave_vk_commission_date: str = ""
    sick_leave_vk_work_org: str = ""
    sick_leave_vk_position: str = ""
    # Совместимость со старой сборкой, где поле было одним.
    sick_leave_vk_work_position: str = ""
    commission_date: str = ""
    commission_number: str = ""

    doctor: str = "Балаганин С.В"
    head: str = "Можарова Е.А."

    warnings: List[str] = field(default_factory=list)

    def lab_dates(self) -> Dict[str, str]:
        result = {"day1": "", "day2": "", "flg": ""}
        from medical_formatting import parse_date

        dt = parse_date(self.admission_date)
        if not dt:
            return result
        result["day1"] = (dt + timedelta(days=1)).strftime(DATE_FMT)
        result["day2"] = (dt + timedelta(days=2)).strftime(DATE_FMT)
        result["flg"] = (dt - timedelta(days=27)).strftime(DATE_FMT)
        return result

    def missing_critical_fields(self) -> List[str]:
        missing = []
        if not self.fio:
            missing.append("Ф.И.О.")
        if not self.birth:
            missing.append("год/дата рождения")
        if not self.admission_date:
            missing.append("дата госпитализации")
        return missing

    def missing_recommended_fields(self) -> List[str]:
        checks = [
            ("жалобы", self.complaints),
            ("анамнез жизни", self.life_anamnesis),
            ("анамнез заболевания", self.disease_anamnesis),
            ("психический статус", self.mental_status),
            ("диагноз", self.diagnosis),
            ("план лечения", self.treatment_plan),
        ]
        return [name for name, value in checks if not value]
