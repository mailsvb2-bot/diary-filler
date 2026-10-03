"""Calendar-period helpers shared by the license issuer and verifier."""
from __future__ import annotations

import calendar
from datetime import datetime


def add_calendar_month(value: datetime) -> datetime:
    """Return the same clock time one calendar month later.

    If the target month has no matching day (for example January 31 -> February),
    clamp to that month's final calendar day.
    """
    if value.month == 12:
        year, month = value.year + 1, 1
    else:
        year, month = value.year, value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
