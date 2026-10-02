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
    date_token = r"([0-9]{4,8}|[0-9]{1,2}(?:[./-][0-9]{1,2}(?:[./-][0-9]{2,4})?)?)"

    # Real primary documents often use the field label itself as the positive
    # decision and write only the value tail: «Больничный лист с 01.10.2026»
    # or «Нужен больничный лист с 01.10.2026». The inline parser correctly
    # extracts «с 01.10.2026», so treat an explicit opening-date tail as a
    # positive sick-leave fact instead of requiring an extra «да/нужен».
    opened_directly = re.search(
        rf"^(?:с|от)\s+{date_token}(?=$|[\s,.;])",
        normalized,
    )
    if opened_directly:
        return "да", opened_directly.group(1)

    positive = re.search(
        rf"\b(?:да|нужен|нужна|нужно|открыт|открыта)\b(?:\s*[,;:-]?\s*с\s+{date_token}(?=$|[\s,.;]))?",
        normalized,
    )
    if positive:
        return "да", (positive.group(1) or "")
    return "", ""


def parse_psych_account_value(value: str) -> tuple[str, str]:
    """Parse rendered psychiatric-registration text into decision/year."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "", ""
    normalized = text.lower().replace("ё", "е")
    if re.search(r"\bне\s+состоит\b", normalized) or normalize_yes_no(normalized) == "нет":
        return "нет", ""
    if re.search(r"\bсостоит\b", normalized) or normalize_yes_no(normalized) == "да":
        year = re.search(r"\b(19|20)\d{2}\b", normalized)
        return "да", (year.group(0) if year else "")
    return "", ""


_RVK_DISTRICT_STEMS = (
    ("автозаводск", "Автозаводский"),
    ("ленинск", "Ленинский"),
    ("канавинск", "Канавинский"),
    ("канвинск", "Канавинский"),
    ("сормовск", "Сормовский"),
    ("московск", "Московский"),
    ("советск", "Советский"),
    ("нижегородск", "Нижегородский"),
    ("приокск", "Приокский"),
)

_RVK_TOKEN_RE = re.compile(
    r"(?iu)(?:\bрвк\b|военком\w*|военн\w*\s+комиссариат\w*)"
)
_RVK_ACTION_RE = re.compile(
    r"(?iu)(?:направлен\w*|госпитализ\w*|поступ\w*|доставлен\w*)"
)
_RVK_EXPLICIT_LABEL_RE = re.compile(
    r"(?iu)(?:^\s*направлени\w*\s+(?:от|из)\s+(?:рвк|военком\w*|военн\w*\s+комиссариат\w*)|"
    r"^\s*(?:рвк|военкомат\w*)\s*[:;,.—–-])"
)


def _extract_known_rvk_districts(value: str) -> str:
    """Return canonical city district names found in an RVK phrase."""
    text = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    if not text:
        return ""
    if re.search(r"(?iu)\b(?:област|край|республик|округ)\w*\b", text):
        return ""

    found: list[str] = []
    for stem, canonical in _RVK_DISTRICT_STEMS:
        if re.search(rf"(?iu)\b{re.escape(stem)}\w*\b", text):
            if canonical not in found:
                found.append(canonical)

    if not found:
        return ""
    if "Сормовский" in found and "Московский" in found:
        others = [item for item in found if item not in {"Сормовский", "Московский"}]
        combined = "Сормовский и Московский"
        return " и ".join([*others, combined]) if others else combined
    return " и ".join(found)


def normalize_rvk_commissariat_text(value: str) -> str:
    """Normalize a district/commissariat phrase for the existing RVK Act popup."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""

    text = text.strip(" \t,.;:—–-()[]")
    text = re.sub(r"(?iu)^\s*да\s*/\s*нет\s*[:;,.—–-]?\s*", "", text)
    text = re.sub(r"(?iu)^\s*(?:да|есть|имеется)\b\s*[:;,.—–-]?\s*", "", text)
    text = re.sub(r"(?iu)^\s*(?:по\s+направлени\w*\s+)?(?:от|из)\s+", "", text)
    text = re.sub(
        r"(?iu)^\s*(?:рвк|военком\w*|военн\w*\s+комиссариат\w*)\s*[:;,.—–-]?\s*",
        "",
        text,
    )
    text = text.strip(" \t,.;:—–-()[]")
    if not text:
        return ""

    known = _extract_known_rvk_districts(text)
    if known:
        return known

    if re.search(
        r"(?iu)\b(?:диагноз|жалоб|анамнез|больничн|должност|место\s+работы|"
        r"ф\.?\s*и\.?\s*о\.?|год\s+рождения|дата\s+рождения|"
        r"психическ\w+\s+статус|соматическ\w+\s+статус|лечение)\b",
        text,
    ):
        return ""

    normalized = text.lower().replace("ё", "е")
    if normalized in {"да", "нет", "да нет"}:
        return ""

    text = re.sub(
        r"(?iu)\s+(?:район(?:а|ов|у|е|ом)?|военком\w*)\s*$",
        "",
        text,
    ).strip(" \t,.;:—–-()[]")
    return text


def parse_rvk_referral_text(text: str) -> tuple[str, str]:
    """Recover RVK referral decision and commissariat from a full medical text."""
    lines = [" ".join(line.split()) for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return "", ""

    candidates: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not _RVK_TOKEN_RE.search(line):
            continue
        explicit = bool(_RVK_EXPLICIT_LABEL_RE.search(line))
        has_action = bool(_RVK_ACTION_RE.search(line))
        if explicit or has_action:
            candidates.append((index, line))

    candidates.sort(
        key=lambda item: (
            0 if _RVK_EXPLICIT_LABEL_RE.search(item[1]) else 1,
            item[0],
        )
    )

    for index, line in candidates:
        decision_line = re.sub(r"(?iu)\bда\s*/\s*нет\b", "", line)
        if (
            re.search(
                r"(?iu)\bбез\s+направлени\w*(?:\s+из|\s+от)?\s*"
                r"(?:рвк|военком\w*|военн\w*\s+комиссариат\w*)",
                decision_line,
            )
            or re.search(
                r"(?iu)\bне\s+(?:направлен\w*|госпитализ\w*|поступ\w*)\b",
                decision_line,
            )
            or re.search(
                r"(?iu)(?:\bрвк\b|военком\w*|военн\w*\s+комиссариат\w*)"
                r".*?[:;,.—–-]?\s*\bнет\b",
                decision_line,
            )
        ):
            return "нет", ""

        area = _extract_known_rvk_districts(line)
        if not area:
            rvk_match = _RVK_TOKEN_RE.search(line)
            if rvk_match:
                area = normalize_rvk_commissariat_text(line[rvk_match.end():])

        if not area and index + 1 < len(lines):
            next_line = lines[index + 1]
            if not _RVK_ACTION_RE.search(next_line):
                area = normalize_rvk_commissariat_text(next_line)

        if area:
            return "да", area

        structured_label = bool(_RVK_EXPLICIT_LABEL_RE.search(line))
        explicit_positive = bool(
            re.search(r"(?iu)\bда\b", decision_line)
            or (
                not structured_label
                and re.search(
                    r"(?iu)(?:по\s+направлени\w+|"
                    r"(?:направлен\w*|госпитализ\w*|поступ\w*)\s+(?:от|из)\s+)",
                    decision_line,
                )
            )
        )
        if explicit_positive:
            return "да", ""

    return "", ""


def parse_rvk_referral_value(value: str) -> tuple[str, str]:
    """Parse an already-extracted RVK field value into decision and area."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "", ""
    normalized = text.lower().replace("ё", "е")
    exact = normalize_yes_no(normalized)
    if exact:
        return exact, ""
    if normalized in {"не по направлению", "не направлялся"}:
        return "нет", ""

    status, area = parse_rvk_referral_text(text)
    if status:
        return status, area

    area = normalize_rvk_commissariat_text(text)
    return ("да", area) if area else ("", "")

def normalize_admission_occurrence(value: str) -> str:
    """Return the canonical episode occurrence selected by the doctor."""
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    return normalized if normalized in ADMISSION_OCCURRENCE_OPTIONS else ""


def parse_admission_occurrence_value(value: str) -> str:
    """Recover an explicit первично/повторно fact from a rendered admission line."""
    normalized = " ".join(str(value or "").strip().lower().replace("ё", "е").split())
    for option in ADMISSION_OCCURRENCE_OPTIONS:
        if re.match(rf"^{re.escape(option)}(?:$|[\s,.;:–—-])", normalized):
            return option
    return ""


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
        r"(?i)\s*\bцелесообразна\s+госпитализация\b.*$",
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
    psych_account_status: str = ""  # да / нет
    psych_account_since_year: str = ""
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
    rvk_referral_present: str = ""  # да / нет
    rvk_referral_commissariat: str = ""
    admission: str = ""
    # How the patient enters this hospitalization episode; explicitly confirmed in popup.
    admission_occurrence: str = ""  # первично / повторно

    complaints: str = ""
    life_anamnesis: str = ""
    disease_anamnesis: str = ""
    mental_status: str = ""
    somatic_status: str = ""
    examination_plan: str = ""
    investigation_results: str = ""
    treatment_plan: str = ""
    # Explicit source/doctor-owned discharge advice. Never synthesize this from
    # bundled template examples.
    discharge_recommendations: str = ""
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
    deputy_chief: str = "Зуйкова А.А."

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
