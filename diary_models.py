"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

@dataclass
class FillResult:
    filled_rows: int
    detected_rows: int
    month_cells_filled: int
    final_rows_filled: int
    next_status_index: int
    gender_replacements: int = 0
    removed_holiday_rows: int = 0
    removed_after_discharge_rows: int = 0


@dataclass
class DiaryBatchResult:
    created_files: list[Path]
    report_path: Path | None
    processed_files: int
    filled_rows: int
    detected_rows: int
    month_cells_filled: int
    final_rows_filled: int
    gender_replacements: int
    removed_holiday_rows: int
    removed_after_discharge_rows: int
