"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import re
from datetime import date

from diary_constants import FULL_DATE_RE, MONTH_YEAR_RE
from diary_text_parser import normalize_text

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



def _two_digit_year_to_full(year: int) -> int:
    return year + (2000 if year < 70 else 1900) if year < 100 else year


def _candidate_date(year: int, month: int, day: int) -> date | None:
    year = _two_digit_year_to_full(year)
    if year < 1900 or year > 2200:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_compact_date_digits(digits: str) -> date | None:
    """Parse compact no-separator dates, including 1126 -> 01.01.2026."""
    if not re.fullmatch(r"\d{4,8}", digits or ""):
        return None

    def make(d_len: int, m_len: int, y_len: int) -> date | None:
        if d_len + m_len + y_len != len(digits):
            return None
        day = int(digits[:d_len])
        month = int(digits[d_len:d_len + m_len])
        year = int(digits[d_len + m_len:])
        return _candidate_date(year, month, day)

    if len(digits) == 8:
        patterns = [(2, 2, 4)]
    elif len(digits) == 6:
        patterns = [(2, 2, 2)]
    elif len(digits) == 4:
        patterns = [(1, 1, 2)]
    elif len(digits) == 5:
        patterns = [(2, 1, 2), (1, 2, 2)] if int(digits[:2]) > 12 else [(1, 2, 2), (2, 1, 2)]
    elif len(digits) == 7:
        patterns = [(2, 1, 4), (1, 2, 4)] if int(digits[:2]) > 12 else [(1, 2, 4), (2, 1, 4)]
    else:
        patterns = []
    for pattern in patterns:
        parsed = make(*pattern)
        if parsed:
            return parsed
    return None

def parse_full_date(text: str) -> date:
    value = re.sub(r"\s*(?:г\.?|год)\s*$", "", normalize_text(text), flags=re.IGNORECASE).strip()
    match = FULL_DATE_RE.fullmatch(value)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        parsed = _candidate_date(year, month, day)
    else:
        # Поддержка ввода без точек: 10052026, 100526 и 1126.
        parsed = _parse_compact_date_digits(value)
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
