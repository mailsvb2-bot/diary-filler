"""Date detection helpers for diary tables."""
from __future__ import annotations

from pathlib import Path

from docx import Document

from diary_dates import parse_month_year
from diary_text_parser import normalize_text
from diary_table_columns import find_day_column, find_month_year_column, is_data_row

def detect_first_month_year_from_docx(path: str | Path) -> tuple[int, int] | None:
    try:
        doc = Document(str(path))
        for table in doc.tables:
            month_year_col = find_month_year_column(table)
            day_col = find_day_column(table)
            if month_year_col is None:
                continue
            for row in table.rows:
                if not is_data_row(row, day_col):
                    continue
                if len(row.cells) <= month_year_col:
                    continue
                value = normalize_text(row.cells[month_year_col].text)
                try:
                    return parse_month_year(value)
                except ValueError:
                    continue
    except Exception:
        return None
    return None
