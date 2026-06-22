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
from diary_table_columns import find_day_column, find_diary_column, find_month_year_column, is_data_row

def remove_row(row) -> None:
    tr = row._tr
    parent = tr.getparent()
    if parent is not None:
        parent.remove(tr)

def collect_dated_entries(doc, start_month: int, start_year: int) -> list[dict]:
    entries: list[dict] = []
    current_month = start_month
    current_year = start_year
    previous_day: int | None = None

    for table in doc.tables:
        diary_col = find_diary_column(table)
        day_col = find_day_column(table)
        month_year_col = find_month_year_column(table)
        if diary_col is None:
            continue
        for row in table.rows:
            if not is_data_row(row, day_col):
                continue
            if len(row.cells) <= diary_col:
                continue
            day_value: int | None = None
            if day_col is not None and len(row.cells) > day_col:
                day_value = cell_int(row.cells[day_col].text)
            if day_value is not None and previous_day is not None and day_value < previous_day:
                current_month, current_year = add_month(current_month, current_year)
            current_date = safe_row_date(current_year, current_month, day_value)
            entries.append(
                {
                    "row": row,
                    "diary_col": diary_col,
                    "day_col": day_col,
                    "month_year_col": month_year_col,
                    "day": day_value,
                    "month": current_month,
                    "year": current_year,
                    "date": current_date,
                }
            )
            if day_value is not None:
                previous_day = day_value
    return entries
