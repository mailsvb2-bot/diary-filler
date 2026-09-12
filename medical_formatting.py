"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from medical_constants import DATE_FMT
from medical_text_utils import normalize_text
from shared_dates import parse_date_value
from shared_paths import resolve_available_path, sanitize_filename

def format_date_with_russian_year_suffix(value: str) -> str:
    """Return UI date text with exactly one trailing " г." for document headers."""
    value = normalize_text(value)
    if not value:
        return ""
    value = re.sub(r"\s*(?:г\.?|год)\s*$", "", value, flags=re.IGNORECASE).strip()
    return f"{value} г."


def format_birth_for_person_line(value: str) -> str:
    """Format birth value for compact lines without duplicating ``г.р.``."""
    value = normalize_text(value)
    if not value:
        return ""
    if re.search(r"г\.?\s*р\.?(?:\s|$)", value, flags=re.IGNORECASE):
        return value
    return f"{value} г.р."


# -----------------------------------------------------------------------------
# Расчёт сроков лечения
# -----------------------------------------------------------------------------

def calculate_inclusive_treatment_days(admission_date: str, commission_date: str) -> int | None:
    """Количество дней лечения от даты поступления до даты комиссии включительно."""
    start = parse_date(admission_date)
    finish = parse_date(commission_date)
    if not start or not finish:
        return None
    days = (finish.date() - start.date()).days + 1
    return days if days >= 1 else None


def _decline_russian_district_name(value: str) -> str:
    """Return genitive masculine form for common district names.

    Нужно для фразы: "военного комиссариата <...> района".
    Врач вводит привычно "Автозаводский"/"Ленинский"/"Сормовский",
    а документ должен получить "Автозаводского"/"Ленинского"/"Сормовского".
    """
    value = normalize_text(value).strip(" .,;:")
    if not value:
        return ""
    low = value.lower().replace("ё", "е")
    explicit = {
        "автозаводский": "Автозаводского",
        "автозаводского": "Автозаводского",
        "ленинский": "Ленинского",
        "ленинского": "Ленинского",
        "советский": "Советского",
        "советского": "Советского",
        "московский": "Московского",
        "московского": "Московского",
        "канавинский": "Канавинского",
        "канавинского": "Канавинского",
        # Частая опечатка пользователя/документа без второй "а".
        "канвинский": "Канавинского",
        "канвинского": "Канавинского",
        "нижегородский": "Нижегородского",
        "нижегородского": "Нижегородского",
        "приокский": "Приокского",
        "приокского": "Приокского",
        "сормовский": "Сормовского",
        "сормовского": "Сормовского",
    }
    if low in explicit:
        return explicit[low]
    if low.endswith(("ского", "цкого", "ого")):
        return value
    if low.endswith("ский"):
        return value[:-4] + "ского"
    if low.endswith("цкий"):
        return value[:-4] + "цкого"
    if low.endswith(("ый", "ой")):
        return value[:-2] + "ого"
    return value


def _normalize_commissariat_input(value: str) -> tuple[str, bool, bool]:
    """Return (name, explicit_commissariat_prefix, explicit_district_suffix)."""
    text = normalize_text(value).strip(" .,;")
    if not text:
        return "", False, False
    text = re.sub(r"^по\s+направлению\s+из\s+", "", text, flags=re.IGNORECASE).strip(" .,;")
    prefix_re = r"^(?:военного\s+комиссариата|военный\s+комиссариат|военкомата|военкомат)\s+"
    explicit_prefix = bool(re.match(prefix_re, text, flags=re.IGNORECASE))
    text = re.sub(prefix_re, "", text, flags=re.IGNORECASE).strip(" .,;")
    text = re.sub(
        r"\s+(?:военного\s+комиссариата|военный\s+комиссариат|военкомата|военкомат)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .,;")
    district_suffix = bool(re.search(r"\s+район(?:а|у|е|ом)?\s*$", text, flags=re.IGNORECASE))
    if district_suffix:
        text = re.sub(r"\s+район(?:а|у|е|ом)?\s*$", "", text, flags=re.IGNORECASE).strip(" .,;")
    return text, explicit_prefix, district_suffix


def _looks_like_complete_commissariat_area(value: str) -> bool:
    """Recognize non-district territorial names that must not gain «района»."""
    low = normalize_text(value).lower().replace("ё", "е")
    if not low:
        return False
    return bool(
        re.search(
            r"(?:\bобласт(?:ь|и|ью|е)\b|\bкра(?:й|я|ю|ем|е)\b|"
            r"\bреспублик(?:а|и|у|ой|е)\b|\bокруг(?:а|у|е|ом)?\b|"
            r"\bгород(?:а|у|е|ом)?\b|(?:^|\s)г\.\s*)",
            low,
            flags=re.IGNORECASE,
        )
    )


def _normalize_district_list(base: str) -> str:
    tokens = re.split(r"(\s+и\s+|\s*,\s*|\s*/\s*|\s*\\\s*)", base, flags=re.IGNORECASE)
    out: list[str] = []
    for token in tokens:
        if not token:
            continue
        if re.fullmatch(r"\s+и\s+", token, flags=re.IGNORECASE):
            out.append(" и ")
        elif re.fullmatch(r"\s*,\s*", token):
            out.append(", ")
        elif re.fullmatch(r"\s*/\s*|\s*\\\s*", token):
            out.append(" и ")
        else:
            out.append(_decline_russian_district_name(token))
    return re.sub(r"\s+", " ", "".join(out).strip(" ,;"))


def format_military_commissariat_area(value: str) -> str:
    """Format the part after «военного комиссариата» in the RVK act.

    Short district choices are declined and gain «района».  Arbitrary complete
    commissariat names from the manual field (for example «Нижегородской
    области») are preserved instead of being corrupted into «... области района».
    """
    base, explicit_prefix, district_suffix = _normalize_commissariat_input(value)
    if not base:
        return ""
    if not district_suffix and (explicit_prefix or _looks_like_complete_commissariat_area(base)):
        return base
    normalized = _normalize_district_list(base)
    return f"{normalized} района" if normalized else ""


def format_military_commissariat_referral(value: str) -> str:
    """Format the primary-exam referral phrase without corrupting custom names."""
    base, explicit_prefix, district_suffix = _normalize_commissariat_input(value)
    if not base:
        return ""
    if not district_suffix and (explicit_prefix or _looks_like_complete_commissariat_area(base)):
        return f"По направлению из военного комиссариата {base}"
    normalized = _normalize_district_list(base)
    return f"По направлению из {normalized} военкомата" if normalized else ""

def russian_day_word(days: int) -> str:
    if 11 <= days % 100 <= 14:
        return "дней"
    last = days % 10
    if last == 1:
        return "день"
    if 2 <= last <= 4:
        return "дня"
    return "дней"


def treatment_period_text(admission_date: str, commission_date: str) -> str:
    days = calculate_inclusive_treatment_days(admission_date, commission_date)
    if admission_date and days:
        return f"Находится на лечении с {admission_date} ({days} {russian_day_word(days)})"
    if admission_date:
        return f"Находится на лечении с {admission_date} (всего дней)"
    return "Находится на лечении с (всего дней)"


def parse_date(value: str) -> Optional[datetime]:
    parsed = parse_date_value(normalize_text(value))
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day)

def safe_filename(value: str) -> str:
    return sanitize_filename(
        value,
        normalizer=normalize_text,
        max_length=80,
        default="Пациент",
    )


def available_path(path: Path) -> Path:
    return resolve_available_path(path, style="paren")

def strip_leading_epi_label(text: str) -> str:
    """Убирает дублирующую метку из ЭПИ-файла: «ЭПИ: ...» -> «...»."""
    text = normalize_text(text)
    text = re.sub(r"^эпи\s*[:()№N#.-]*\s*", "", text, flags=re.IGNORECASE)
    return text.strip()
