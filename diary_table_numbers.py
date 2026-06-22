"""Small numeric/date helpers for diary tables."""
from __future__ import annotations

import re
from datetime import date

from diary_constants import HOLIDAY_SKIP_END_DAY, HOLIDAY_SKIP_MONTHS, HOLIDAY_SKIP_START_DAY
from diary_text_parser import normalize_text


def cell_int(text: str) -> int | None:
    value = normalize_text(text)
    match = re.fullmatch(r"0*(\d{1,2})", value)
    if not match:
        return None
    result = int(match.group(1))
    return result if 1 <= result <= 31 else None

def is_holiday_skip_date(day: int | None, month: int) -> bool:
    """Return True for rows dated 01.01-09.01 and 01.05-09.05."""
    return (
        day is not None
        and month in HOLIDAY_SKIP_MONTHS
        and HOLIDAY_SKIP_START_DAY <= day <= HOLIDAY_SKIP_END_DAY
    )

def should_remove_holiday(row_date: date | None) -> bool:
    if row_date is None:
        return False
    return (
        row_date.month in HOLIDAY_SKIP_MONTHS
        and HOLIDAY_SKIP_START_DAY <= row_date.day <= HOLIDAY_SKIP_END_DAY
    )
