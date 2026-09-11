"""Canonical date parsing shared by medical documents and diaries.

This module is deliberately UI- and DOCX-independent.  Callers may normalize
text for their own domain first, but all calendar interpretation lives here so
compact dates cannot drift between popup, medical and diary paths.
"""

from __future__ import annotations

import re
from datetime import date

MIN_CLINICAL_YEAR = 1900
MAX_CLINICAL_YEAR = 2200
_YEAR_SUFFIX_RE = re.compile(r"\s*(?:г\.?|год)\s*$", re.IGNORECASE)
_SEPARATED_DATE_RE = re.compile(
    r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2}|\d{4})"
)
_COMPACT_DATE_RE = re.compile(r"\d{4,8}")


def _two_digit_year_to_full(year: int) -> int:
    return year + (2000 if year < 70 else 1900) if year < 100 else year


def _candidate_date(year: int, month: int, day: int) -> date | None:
    year = _two_digit_year_to_full(year)
    if year < MIN_CLINICAL_YEAR or year > MAX_CLINICAL_YEAR:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_compact_date_digits(digits: str) -> date | None:
    """Parse compact dates such as 10052026, 100526 and 1126."""
    if not _COMPACT_DATE_RE.fullmatch(digits or ""):
        return None

    def make(day_len: int, month_len: int, year_len: int) -> date | None:
        if day_len + month_len + year_len != len(digits):
            return None
        day = int(digits[:day_len])
        month = int(digits[day_len:day_len + month_len])
        year = int(digits[day_len + month_len:])
        return _candidate_date(year, month, day)

    if len(digits) == 8:
        patterns = ((2, 2, 4),)
    elif len(digits) == 6:
        patterns = ((2, 2, 2),)
    elif len(digits) == 4:
        patterns = ((1, 1, 2),)
    elif len(digits) == 5:
        patterns = ((2, 1, 2), (1, 2, 2)) if int(digits[:2]) > 12 else ((1, 2, 2), (2, 1, 2))
    elif len(digits) == 7:
        patterns = ((2, 1, 4), (1, 2, 4)) if int(digits[:2]) > 12 else ((1, 2, 4), (2, 1, 4))
    else:
        patterns = ()

    for pattern in patterns:
        parsed = make(*pattern)
        if parsed is not None:
            return parsed
    return None


def parse_date_value(value: str) -> date | None:
    """Return one canonical clinical date or ``None`` for invalid input.

    The accepted forms intentionally preserve the application's established
    contract: D.M.YY / DD.MM.YYYY (also slash or hyphen separators), compact
    DDMMYY/DDMMYYYY, and short compact forms with omitted leading zeroes such
    as 1126 -> 01.01.2026.
    """
    value = _YEAR_SUFFIX_RE.sub("", str(value or "")).strip()
    if not value:
        return None

    match = _SEPARATED_DATE_RE.fullmatch(value)
    if match:
        return _candidate_date(
            int(match.group(3)),
            int(match.group(2)),
            int(match.group(1)),
        )
    return _parse_compact_date_digits(value)
