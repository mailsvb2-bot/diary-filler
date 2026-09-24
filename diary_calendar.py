"""Shared production-calendar rules for diary scheduling.

The calendar separates public-holiday dates from generic weekends because
ordinary diary cleanup removes public-holiday rows only, while dynamic
epicrises must avoid every non-working day.
"""
from __future__ import annotations

from datetime import date


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
# Annual production-calendar exceptions are explicit. Never infer a transferred
# weekday from the weekday on which a holiday happens to fall: the Government
# can transfer that day elsewhere in the year.
#
# 2025: Government Resolution No. 1335 of 04.10.2024.
# 2026: statutory weekend compensation for 08.03/09.05 plus Government
# Resolution No. 1466 of 24.09.2025 for 09.01 and 31.12.
YEAR_SPECIFIC_NON_WORKING_DATES: dict[int, frozenset[tuple[int, int]]] = {
    2025: frozenset({(5, 2), (5, 8), (6, 13), (11, 3), (12, 31)}),
    2026: frozenset({(1, 9), (3, 9), (5, 11), (12, 31)}),
}

# A transferred weekend can become a working day. This must also be explicit;
# for example, 01.11.2025 is a working Saturday because its day off moved to
# 03.11.2025.
YEAR_SPECIFIC_WORKING_DATES: dict[int, frozenset[tuple[int, int]]] = {
    2025: frozenset({(11, 1)}),
}


def is_fixed_holiday(day: date) -> bool:
    return (day.month, day.day) in FIXED_HOLIDAYS


def is_public_holiday(day: date) -> bool:
    if is_fixed_holiday(day):
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
