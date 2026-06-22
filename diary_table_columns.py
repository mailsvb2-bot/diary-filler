"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import re
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from diary_constants import HOLIDAY_SKIP_END_DAY, HOLIDAY_SKIP_MONTHS, HOLIDAY_SKIP_START_DAY, STATUS_FONT_SIZE_PT, STRUCTURAL_DIARY_PREFIXES
from diary_dates import add_month, format_month_year, parse_month_year, safe_row_date
from diary_text_parser import is_signature_paragraph_text, normalize_text, remove_examinee_words
from diary_table_numbers import cell_int

def is_data_row(row, day_col: int | None = None, hospitalization_day_col: int | None = None) -> bool:
    """Return True for diary data rows.

    Some templates already contain calendar days in the «Число» column; others
    leave «Число» empty and rely only on «День госпитализации». The old check
    looked only at «Число», so such rows were skipped and dates/texts were not
    filled.
    """
    if not row.cells:
        return False
    if day_col is not None and len(row.cells) > day_col and cell_int(row.cells[day_col].text) is not None:
        return True
    if hospitalization_day_col is not None and len(row.cells) > hospitalization_day_col and cell_int(row.cells[hospitalization_day_col].text) is not None:
        return True
    first = normalize_text(row.cells[0].text)
    return bool(re.fullmatch(r"\d+", first))

def find_column_by_header(table, keywords: tuple[str, ...], *, fallback: int | None = None) -> int | None:
    if not table.rows:
        return fallback
    max_header_rows = min(5, len(table.rows))
    for row in table.rows[:max_header_rows]:
        for index, cell in enumerate(row.cells):
            text = normalize_text(cell.text).lower().replace(" ", "")
            if all(keyword.replace(" ", "") in text for keyword in keywords):
                return index
    return fallback

def find_diary_column(table) -> int | None:
    if not table.rows:
        return None
    for row in table.rows[: min(5, len(table.rows))]:
        for index, cell in enumerate(row.cells):
            text = normalize_text(cell.text).lower()
            if "дневник" in text or "наблюдения" in text:
                return index
    return len(table.rows[0].cells) - 1 if table.rows[0].cells else None

def find_day_column(table) -> int | None:
    if not table.rows or not table.rows[0].cells:
        return None
    col = find_column_by_header(table, ("число",), fallback=None)
    if col is not None:
        return col
    return 1 if len(table.rows[0].cells) >= 3 else 0

def find_hospitalization_day_column(table) -> int | None:
    """Return the column with the hospitalization day number.

    In the diary templates this is the first service column named like
    "День госпитализации". It is intentionally separate from the
    calendar day column "Число".
    """
    if not table.rows or not table.rows[0].cells:
        return None
    for row in table.rows[: min(5, len(table.rows))]:
        for index, cell in enumerate(row.cells):
            text = normalize_text(cell.text).lower().replace(" ", "")
            if "госпит" in text and ("день" in text or "ализа" in text):
                return index
    return None

def find_month_year_column(table) -> int | None:
    if not table.rows or not table.rows[0].cells:
        return None
    for row in table.rows[: min(5, len(table.rows))]:
        for index, cell in enumerate(row.cells):
            text = normalize_text(cell.text).lower().replace(" ", "")
            if "месяц" in text and ("год" in text or "/" in text):
                return index
    return 2 if len(table.rows[0].cells) >= 4 else None
