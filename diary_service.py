"""Production service boundary for user-facing text diaries."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence

from docx import Document

from diary_batch import _clinical_diary_offsets, create_text_diaries
from diary_dates import parse_full_date, parse_optional_discharge_date
from diary_models import DiaryBatchResult


class DiaryService:
    """Create the paragraph-based clinical diary used by the GUI.

    The legacy table writer intentionally is not exposed here. This keeps the
    production UI on one diary architecture while old integrations can continue
    using ``fill_diary_batch`` during the compatibility period.
    """

    @staticmethod
    def _make_fallback_date_source(
        directory: Path,
        *,
        admission_value: str,
        discharge_value: str,
    ) -> Path:
        """Create an ephemeral date source when no 01–31 set was supplied.

        A manually selected diary-text Word file is the doctor's explicit source
        of clinical wording. Numbered date files are optional calendar metadata;
        when absent (or when a remembered folder contains only text files), use
        the proven clinical cadence and never reject the selected text source.
        The temporary DOCX is deleted immediately after generation.
        """
        admission = parse_full_date(admission_value)
        discharge = parse_optional_discharge_date(discharge_value)
        max_offset = (discharge - admission).days if discharge is not None else 7
        path = directory / "generated-clinical-diary-dates.docx"
        doc = Document()
        for offset in _clinical_diary_offsets(max_offset):
            doc.add_paragraph((admission + timedelta(days=offset)).strftime("%d.%m.%Y"))
        doc.save(str(path))
        return path

    @staticmethod
    def _persistent_fallback_output_dir(
        output_dir: str | Path | None,
        status_files: Sequence[str | Path],
    ) -> str | Path:
        """Choose a persistent destination before creating the temporary Dates source."""
        if output_dir is not None and str(output_dir).strip():
            return output_dir
        for raw_path in status_files:
            if raw_path is not None and str(raw_path).strip():
                return Path(raw_path).expanduser().parent
        return Path.cwd()

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
        doctor_name: str = "",
        department_head_name: str = "",
    ) -> DiaryBatchResult:
        if diary_files:
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
                doctor_name=doctor_name,
                department_head_name=department_head_name,
            )

        # No numbered date template: the explicitly selected text file remains
        # authoritative. Resolve output against persistent inputs before entering
        # the temporary date-source directory, otherwise output_dir=None would
        # write the finished diary into that directory and delete it on return.
        persistent_output_dir = self._persistent_fallback_output_dir(output_dir, status_files)
        with TemporaryDirectory(prefix=".diary-date-source-") as tmp_dir:
            fallback = self._make_fallback_date_source(
                Path(tmp_dir),
                admission_value=admission_value,
                discharge_value=discharge_value,
            )
            return create_text_diaries(
                status_files=status_files,
                diary_files=[fallback],
                output_dir=persistent_output_dir,
                patient_name=patient_name,
                admission_value=admission_value,
                gender_source_name=gender_source_name,
                discharge_value=discharge_value,
                repeat_statuses=repeat_statuses,
                force_final_diary=force_final_diary,
                write_report=write_report,
                doctor_name=doctor_name,
                department_head_name=department_head_name,
            )
