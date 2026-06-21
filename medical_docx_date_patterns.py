from __future__ import annotations

import re
from datetime import datetime

from medical_constants import DATE_FMT
from medical_formatting import parse_date

_TITLE_DATE_RE = re.compile(
    r"(?<!\d)(?:(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})|(\d{4,8}))(?!\d)"
)


def _normalize_full_date_match(match: re.Match[str]) -> str:
    value = match.group(1) or match.group(2) or ""
    parsed = parse_date(value)
    return parsed.strftime(DATE_FMT) if parsed else ""


def _first_valid_full_date(value: str) -> str:
    for match in _TITLE_DATE_RE.finditer(value or ""):
        normalized = _normalize_full_date_match(match)
        if normalized:
            return normalized
    return ""
