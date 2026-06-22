"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Sequence

from medical_docx_editor import DocxBlockEditor
from medical_formatting import calculate_inclusive_treatment_days, parse_date, russian_day_word
from medical_models import PatientData
from medical_text_utils import normalize_text

def normalize_yes_no(value: str) -> str:
    value = normalize_text(value).lower().replace("ё", "е")
    if value in {"да", "д", "yes", "y", "1", "+", "работает", "нужен", "нужна", "нужно"}:
        return "да"
    if value in {"нет", "н", "no", "n", "0", "-", "не работает", "не нужен", "не нужна", "не нужно"}:
        return "нет"
    return ""


def return_to_work_date(discharge_date: str) -> str:
    """Дата выхода к труду: следующий календарный день после выписки."""
    finish = parse_date(discharge_date)
    if not finish:
        return ""
    return (finish + timedelta(days=1)).strftime("%d.%m.%Y")


def build_expert_anamnesis(
    data: PatientData,
    *,
    include_sick_leave_number: bool = True,
    include_sick_leave: bool = True,
    include_return_to_work: bool = True,
) -> str:
    """Собрать строку экспертного анамнеза из UI-данных.

    Для первичного осмотра используется короткий вариант: только работа и
    должность, без номера ЛН, срока лечения и даты выхода к труду. Для
    выписного эпикриза используется полный вариант.
    """
    work_status = normalize_yes_no(data.expert_work_status)
    sick_needed = normalize_yes_no(data.expert_sick_leave_needed)
    org = normalize_text(data.expert_work_org or data.work_org)
    position = normalize_text(data.expert_position or data.position)
    sick_from = normalize_text(data.expert_sick_leave_from)
    sick_number = normalize_text(getattr(data, "expert_sick_leave_number", "")) if include_sick_leave_number else ""

    if not work_status:
        joined = f"{org} {position}".lower().replace("ё", "е")
        if "не работает" in joined:
            work_status = "нет"
        elif org or position:
            work_status = "да"

    if not sick_needed and data.sick_leave:
        low = data.sick_leave.lower().replace("ё", "е")
        if "не нуж" in low or low.strip() == "нет":
            sick_needed = "нет"
        elif "нуж" in low or "больнич" in low or "лн" in low:
            sick_needed = "да"

    parts: list[str] = []
    if work_status == "да":
        if org and position:
            parts.append(f"Работает в {org}, в должности {position}.")
        elif org:
            parts.append(f"Работает в {org}.")
        elif position:
            parts.append(f"Работает, должность: {position}.")
        else:
            parts.append("Работает.")
    elif work_status == "нет":
        parts.append("Не работает.")

    if include_sick_leave:
        if sick_needed == "да":
            number_part = f" № {sick_number}" if sick_number else ""
            if include_sick_leave_number and (sick_number or data.discharge_date):
                # В выписном эпикризе не пишем "нужен с ...": нужен номер ЛН,
                # срок лечения и дата выхода к труду.
                line = f"Больничный лист{number_part}."
                start = normalize_text(data.admission_date or sick_from)
                finish = normalize_text(data.discharge_date)
                days = calculate_inclusive_treatment_days(start, finish) if start and finish else None
                if start and finish and days:
                    line += f" Срок лечения с {start} по {finish}, {days} {russian_day_word(days)}."
                elif start and finish:
                    line += f" Срок лечения с {start} по {finish}."
                elif sick_from:
                    line += f" Больничный лист открыт с {sick_from}."
                return_to_work = return_to_work_date(finish) if include_return_to_work else ""
                if return_to_work:
                    line += f" К труду с {return_to_work}."
                parts.append(line)
            else:
                if sick_from:
                    parts.append(f"Больничный лист{number_part} нужен с {sick_from}.")
                else:
                    parts.append(f"Больничный лист{number_part} нужен.")
        elif sick_needed == "нет":
            parts.append("В выдаче ЛН не нуждается.")

    return " ".join(parts).strip()


def put_expert_anamnesis(
    editor: DocxBlockEditor,
    data: PatientData,
    all_markers: Sequence[str],
    before_markers: Sequence[str],
    *,
    include_sick_leave_number: bool = True,
    include_sick_leave: bool = True,
    include_return_to_work: bool = True,
    replace_existing: bool = True,
) -> bool:
    text = build_expert_anamnesis(
        data,
        include_sick_leave_number=include_sick_leave_number,
        include_sick_leave=include_sick_leave,
        include_return_to_work=include_return_to_work,
    )
    if not text:
        return False
    if replace_existing and editor.replace_block(["Экспертный анамнез"], "Экспертный анамнез:", text, all_markers, allow_empty=True):
        return True
    return editor.insert_before_first_matching_paragraph(before_markers, f"Экспертный анамнез: {text}")
