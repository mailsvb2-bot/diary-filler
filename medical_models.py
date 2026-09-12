"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List

from medical_constants import DATE_FMT


ADMISSION_OCCURRENCE_OPTIONS = ("первично", "повторно")


def normalize_yes_no(value: str) -> str:
    """Normalize doctor-facing yes/no decisions to one canonical value."""
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    if normalized in {"да", "д", "yes", "y", "1", "+", "нужен", "нужна", "нужно", "работает"}:
        return "да"
    if normalized in {"нет", "н", "no", "n", "0", "-", "не нужен", "не нужна", "не нужно", "не работает"}:
        return "нет"
    return ""


def parse_sick_leave_value(value: str) -> tuple[str, str]:
    """Parse a rendered sick-leave field into canonical decision/date parts.

    Generated primary documents contain values such as ``не нужен`` or
    ``нужен с 12.06.2026``.  Public service callers may legitimately parse one
    of those documents and feed the resulting ``PatientData`` back into the
    generator, so the rendered representation must round-trip through the same
    service boundary as the explicit popup fields.  Date syntax is deliberately
    left to the service's canonical date parser/validator.
    """
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "", ""
    exact = normalize_yes_no(text)
    if exact:
        return exact, ""
    normalized = text.lower().replace("ё", "е")
    if re.search(r"\bне\s+(?:нужен|нужна|нужно|требуется)\b", normalized):
        return "нет", ""
    match = re.search(
        r"\b(?:нужен|нужна|нужно)\b(?:\s+с\s+([0-9]{4,8}|[0-9]{1,2}(?:[./-][0-9]{1,2}(?:[./-][0-9]{2,4})?)?)(?=$|[\s,.;]))?",
        normalized,
    )
    if match:
        return "да", (match.group(1) or "")
    return "", ""


def normalize_admission_occurrence(value: str) -> str:
    """Return the canonical episode occurrence selected by the doctor."""
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    return normalized if normalized in ADMISSION_OCCURRENCE_OPTIONS else ""


def strip_admission_occurrence_prefix(value: str) -> str:
    """Remove a legacy leading occurrence token from the clinical admission tail.

    ``admission_occurrence`` is an explicit doctor-confirmed fact. The free-text
    ``admission`` field must not carry a second copy of ``первично/повторно``.
    """
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower().replace("ё", "е")
    for option in ADMISSION_OCCURRENCE_OPTIONS:
        if lowered == option:
            return ""
        if lowered.startswith(option):
            boundary = len(option)
            if len(lowered) > boundary and not lowered[boundary].isalpha():
                return text[boundary:].lstrip(" ,.;:–—-")
            if len(lowered) > boundary and lowered[boundary].isspace():
                return text[boundary:].strip()
    return text


def clean_admission_detail(value: str) -> str:
    """Keep only clinically useful tail text after the occurrence selector.

    Legacy primary documents sometimes store a recommendation such as
    «Целесообразна госпитализация ...» in the same field. That sentence must
    not be copied into generated documents; the actual hospitalization fact
    is represented by the canonical «первично/повторно» choice.
    """
    text = strip_admission_occurrence_prefix(value)
    # This recommendation is not an admission-detail fact and must never be
    # copied into generated documents, even when the source omitted punctuation
    # before it (a common legacy-template formatting defect).
    text = re.sub(
        r"(?i)\s*целесообразна\s+госпитализация\b.*$",
        "",
        text,
    )
    return " ".join(text.strip(" ,.;:–—-").split())


def admission_occurrence_label(value: str) -> str:
    occurrence = normalize_admission_occurrence(value)
    return f"В 3 отделение КДП поступает {occurrence}".strip()

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
    disability_needed: str = ""  # да / нет
    disability: str = ""
    rvk_referral: str = ""
    admission: str = ""
    # How the patient enters this hospitalization episode; explicitly confirmed in popup.
    admission_occurrence: str = ""  # первично / повторно

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
    epi_present: str = ""  # да / нет
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
            ("адрес регистрации", self.registered),
            ("жалобы", self.complaints),
            ("анамнез жизни", self.life_anamnesis),
            ("анамнез заболевания", self.disease_anamnesis),
            ("психический статус", self.mental_status),
            ("эпидемиологический анамнез", self.epidemiology),
            ("диагноз", self.diagnosis),
            ("план лечения", self.treatment_plan),
        ]
        return [name for name, value in checks if not value]
