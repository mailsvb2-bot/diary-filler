"""Public facade for diary DOCX filling."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

from docx import Document

from diary_models import FillResult
from diary_writer_apply import apply_diary_entries
from diary_writer_entries import (
    build_dated_entries,
    collect_data_entries,
    find_final_entry_index,
    mark_skip_flags,
)


def fill_diary_file(
    path: str | Path,
    statuses: Sequence[str],
    *,
    start_idx: int = 0,
    repeat_statuses: bool = True,
    keep_signature: bool = True,
    fill_months: bool = True,
    start_month: int,
    start_year: int,
    admission_date_value: date | None = None,
    discharge_date: date | None = None,
    force_final_diary: bool = True,
    remove_holiday_rows: bool = True,
    patient_gender: str | None = None,
) -> FillResult:
    """Fill diary tables in one DOCX template and return a stable summary."""
    doc = Document(str(path))
    data_entries = collect_data_entries(doc)
    dated_entries = build_dated_entries(
        data_entries,
        start_month=start_month,
        start_year=start_year,
        admission_date_value=admission_date_value,
    )
    final_entry_index = find_final_entry_index(
        data_entries,
        dated_entries,
        discharge_date=discharge_date,
        remove_holiday_rows=remove_holiday_rows,
    )
    mark_skip_flags(
        dated_entries,
        final_entry_index=final_entry_index,
        discharge_date=discharge_date,
        remove_holiday_rows=remove_holiday_rows,
    )
    stats = apply_diary_entries(
        data_entries,
        dated_entries,
        statuses,
        start_idx=start_idx,
        repeat_statuses=repeat_statuses,
        keep_signature=keep_signature,
        fill_months=fill_months,
        discharge_date=discharge_date,
        force_final_diary=force_final_diary,
        final_entry_index=final_entry_index,
        patient_gender=patient_gender,
    )
    doc.save(str(path))
    return FillResult(**stats)
