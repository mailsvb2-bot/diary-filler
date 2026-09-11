"""Production service boundary for user-facing text diaries."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from diary_batch import create_text_diaries
from diary_models import DiaryBatchResult


class DiaryService:
    """Create the paragraph-based clinical diary used by the GUI.

    The legacy table writer intentionally is not exposed here. This keeps the
    production UI on one diary architecture while old integrations can continue
    using ``fill_diary_batch`` during the compatibility period.
    """

    def create_text_diaries(
        self,
        *,
        status_files: Sequence[str | Path],
        diary_files: Sequence[str | Path],
        output_dir: str | Path | None,
        patient_name: str,
        admission_value: str,
        gender_source_name: str | None = None,
        discharge_value: str = "",
        repeat_statuses: bool = True,
        force_final_diary: bool = True,
        write_report: bool = False,
    ) -> DiaryBatchResult:
        return create_text_diaries(
            status_files=status_files,
            diary_files=diary_files,
            output_dir=output_dir,
            patient_name=patient_name,
            admission_value=admission_value,
            gender_source_name=gender_source_name,
            discharge_value=discharge_value,
            repeat_statuses=repeat_statuses,
            force_final_diary=force_final_diary,
            write_report=write_report,
        )
