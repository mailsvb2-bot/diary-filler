"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import re
from datetime import date

from diary_constants import MONTH_YEAR_RE
from diary_text_parser import normalize_text
from shared_dates import parse_date_value

def parse_month_year(text: str) -> tuple[int, int]:
    value = re.sub(r"\s*(?:г\.?|год)\s*$", "", normalize_text(text), flags=re.IGNORECASE).strip()
    match = MONTH_YEAR_RE.fullmatch(value)
    if not match:
        raise ValueError("Введите начальный месяц и год в формате ММ.ГГГГ, например 06.2026")
    month = int(match.group(1))
    year = int(match.group(2))
    if month < 1 or month > 12:
        raise ValueError("Месяц должен быть от 01 до 12")
    if year < 1900 or year > 2200:
        raise ValueError("Год выглядит некорректно")
    return month, year



def parse_full_date(text: str) -> date:
    parsed = parse_date_value(normalize_text(text))
    if not parsed:
        raise ValueError("Введите дату в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ, например 11.06.2026, 110626 или 1126")
    return parsed

def parse_admission_month_year(text: str) -> tuple[int, int]:
    value = normalize_text(text)
    try:
        admission_date = parse_full_date(value)
        return admission_date.month, admission_date.year
    except ValueError:
        return parse_month_year(value)


def parse_optional_discharge_date(text: str) -> date | None:
    value = normalize_text(text)
    if not value:
        return None
    return parse_full_date(value)


def safe_row_date(year: int, month: int, day: int | None) -> date | None:
    if day is None:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def add_month(month: int, year: int, delta: int = 1) -> tuple[int, int]:
    month += delta
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    return month, year


def format_month_year(month: int, year: int) -> str:
    return f"{month:02d}.{year:04d}"
