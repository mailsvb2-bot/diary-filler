from __future__ import annotations

from datetime import date
from typing import Sequence

from docx.enum.text import WD_ALIGN_PARAGRAPH

from diary_constants import FINAL_DIARY_TEXT
from diary_dates import format_month_year
from diary_gender import adapt_text_to_patient_gender
from diary_table import fill_diary_text_cell, fill_text_cell, remove_row
from diary_text_parser import clean_status_text, remove_examinee_words
from diary_writer_entries import DatedEntry, DiaryEntry


def apply_diary_entries(
    data_entries: list[DiaryEntry],
    dated_entries: list[DatedEntry],
    statuses: Sequence[str],
    *,
    start_idx: int,
    repeat_statuses: bool,
    keep_signature: bool,
    fill_months: bool,
    discharge_date: date | None,
    force_final_diary: bool,
    final_entry_index: int | None,
    patient_gender: str | None,
) -> dict[str, int]:
    idx = start_idx
    stats = {
        "filled_rows": 0,
        "detected_rows": 0,
        "month_cells_filled": 0,
        "final_rows_filled": 0,
        "gender_replacements": 0,
        "removed_holiday_rows": 0,
        "removed_after_discharge_rows": 0,
    }

    for entry_index, ((row, diary_col, day_col, month_year_col, _hospitalization_day_col), entry) in enumerate(zip(data_entries, dated_entries)):
        stats["detected_rows"] += 1
        skip_after_discharge = bool(entry["skip_after_discharge"])
        skip_holiday = bool(entry["skip_holiday"])

        if skip_after_discharge or skip_holiday:
            remove_row(row)
            if skip_after_discharge:
                stats["removed_after_discharge_rows"] += 1
            else:
                stats["removed_holiday_rows"] += 1
            continue

        row_month = int(entry["month"])
        row_year = int(entry["year"])
        is_final_diary_row = force_final_diary and final_entry_index is not None and entry_index == final_entry_index

        display_day = int(entry["day"]) if isinstance(entry["day"], int) else None
        if is_final_diary_row and discharge_date is not None:
            display_day = discharge_date.day
            row_month = discharge_date.month
            row_year = discharge_date.year

        if day_col is not None and len(row.cells) > day_col and display_day is not None:
            fill_text_cell(row.cells[day_col], f"{display_day:02d}", alignment=WD_ALIGN_PARAGRAPH.CENTER)

        if fill_months and month_year_col is not None and len(row.cells) > month_year_col:
            fill_text_cell(row.cells[month_year_col], format_month_year(row_month, row_year), alignment=WD_ALIGN_PARAGRAPH.CENTER)
            stats["month_cells_filled"] += 1

        if is_final_diary_row:
            adapted_final_text, changed = adapt_text_to_patient_gender(FINAL_DIARY_TEXT, patient_gender)
            adapted_final_text = remove_examinee_words(adapted_final_text)
            stats["gender_replacements"] += changed
            fill_diary_text_cell(row.cells[diary_col], adapted_final_text, keep_signature=keep_signature)
            stats["filled_rows"] += 1
            stats["final_rows_filled"] += 1
            continue

        if not statuses:
            continue
        if idx >= len(statuses):
            if repeat_statuses:
                idx = 0
            else:
                continue

        adapted_status, changed = adapt_text_to_patient_gender(statuses[idx], patient_gender)
        adapted_status = clean_status_text(adapted_status)
        stats["gender_replacements"] += changed
        fill_diary_text_cell(row.cells[diary_col], adapted_status, keep_signature=keep_signature)
        stats["filled_rows"] += 1
        idx += 1

    stats["next_status_index"] = idx
    return stats
