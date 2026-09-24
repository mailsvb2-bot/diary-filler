"""Small numeric/date helpers for diary tables."""
from __future__ import annotations

import re
from datetime import date

from diary_calendar import is_fixed_holiday, is_public_holiday
from diary_text_parser import normalize_text


def cell_int(text: str) -> int | None:
    """Parse a calendar day number (1..31)."""
    value = normalize_text(text)
    match = re.fullmatch(r"0*(\d{1,2})", value)
    if not match:
        return None
    result = int(match.group(1))
    return result if 1 <= result <= 31 else None


def hospitalization_day_int(text: str) -> int | None:
    """Parse an ordinal hospitalization day without the calendar-day 31 limit."""
    value = normalize_text(text)
    match = re.fullmatch(r"0*(\d{1,4})", value)
    if not match:
        return None
    result = int(match.group(1))
    return result if 1 <= result <= 3660 else None

def is_holiday_skip_date(day: int | None, month: int, year: int | None = None) -> bool:
    """Return True for a public-holiday diary row.

    Year-aware callers include statutory transfers. The legacy no-year form can
    only identify fixed statutory holidays and intentionally does not guess.
    """
    if day is None:
        return False
    try:
        probe = date(year if year is not None else 2000, month, day)
    except ValueError:
        return False
    return is_public_holiday(probe) if year is not None else is_fixed_holiday(probe)


def should_remove_holiday(row_date: date | None) -> bool:
    return bool(row_date is not None and is_public_holiday(row_date))
