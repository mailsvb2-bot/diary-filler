"""Shared production-calendar rules for diary scheduling.

The calendar separates public-holiday dates from generic weekends because
ordinary diary cleanup removes public-holiday rows only, while dynamic
epicrises must avoid every non-working day.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


FIXED_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {
        *((1, day) for day in range(1, 9)),
        (2, 23),
        (3, 8),
        (5, 1),
        (5, 9),
        (6, 12),
        (11, 4),
    }
)
JANUARY_HOLIDAYS: frozenset[tuple[int, int]] = frozenset((1, day) for day in range(1, 9))

# Government/year-specific transfers must be explicit. 2026 data is from
# Government Resolution No. 1466 of 24.09.2025.
YEAR_SPECIFIC_NON_WORKING_DATES: dict[int, frozenset[tuple[int, int]]] = {
    2026: frozenset({(1, 9), (12, 31)}),
}

# Some production calendars designate a weekend as a working day. Keep this
# explicit rather than trying to infer it from neighboring holidays.
YEAR_SPECIFIC_WORKING_DATES: dict[int, frozenset[tuple[int, int]]] = {}


def is_fixed_holiday(day: date) -> bool:
    return (day.month, day.day) in FIXED_HOLIDAYS


@lru_cache(maxsize=None)
def automatic_holiday_transfer_dates(year: int) -> frozenset[date]:
    """Derive next-working-day transfers outside the January holiday block."""
    result: set[date] = set()
    for month, day_value in FIXED_HOLIDAYS - JANUARY_HOLIDAYS:
        holiday = date(year, month, day_value)
        if holiday.weekday() < 5:
            continue
        candidate = holiday + timedelta(days=1)
        while candidate.weekday() >= 5 or is_fixed_holiday(candidate):
            candidate += timedelta(days=1)
        result.add(candidate)
    return frozenset(result)


def is_public_holiday(day: date) -> bool:
    if is_fixed_holiday(day):
        return True
    if day in automatic_holiday_transfer_dates(day.year):
        return True
    return (day.month, day.day) in YEAR_SPECIFIC_NON_WORKING_DATES.get(
        day.year, frozenset()
    )


def is_non_working_day(day: date) -> bool:
    if is_public_holiday(day):
        return True
    if (day.month, day.day) in YEAR_SPECIFIC_WORKING_DATES.get(day.year, frozenset()):
        return False
    return day.weekday() >= 5
