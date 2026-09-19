"""Production service boundary for user-facing text diaries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from diary_batch import _clinical_diary_offsets, create_text_diaries
from diary_dates import parse_full_date, parse_optional_discharge_date
from diary_models import DiaryBatchResult


FIXED_HOLIDAY_RANGES: tuple[tuple[int, int, int], ...] = ((1, 1, 9), (5, 1, 9))
_LEADING_DATE_RE = re.compile(r"^\s*([0-3]?\d)[./-]([01]?\d)[./-](\d{2}|20\d{2})(?=\s|$)")


@dataclass(frozen=True)
class DynamicEpicrisisInput:
    patient_name: str = ""
    birth_date: str = ""
    sick_leave_from: str = ""
    complaints: str = ""
    treatment: str = ""
    profile_status: str = ""
    treatment_correction: str = ""
    treating_physician: str = ""
    department_head: str = ""


def is_fixed_holiday(day: date) -> bool:
    return any(month == day.month and start <= day.day <= end for month, start, end in FIXED_HOLIDAY_RANGES)


def is_non_working_day(day: date) -> bool:
    return day.weekday() >= 5 or is_fixed_holiday(day)


def next_working_day(day: date, *, used=()) -> date:
    used_set = set(used)
    current = day
    for _ in range(370):
        if not is_non_working_day(current) and current not in used_set:
            return current
        current += timedelta(days=1)
    raise RuntimeError("Cannot find an available calendar day within one year.")


def _optional_full_date(value: str) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return parse_full_date(text)
    except ValueError:
        return None


def dynamic_epicrisis_base_date(admission: date, sick_leave_from: str) -> date:
    """Use the later of admission and sick-leave start, matching Dokkomplekt."""
    sick_leave_date = _optional_full_date(sick_leave_from)
    return max(admission, sick_leave_date) if sick_leave_date is not None else admission


def dynamic_epicrisis_dates(
    admission: date,
    *,
    discharge_date: date | None = None,
    limit: int = 12,
) -> tuple[date, ...]:
    """Plan each 10-day epicrisis, shifting non-working dates forward.

    The discharge date is a hard exclusive boundary: no dynamic epicrisis is
    created on or after discharge, including after a weekend/holiday shift.
    """
    result: list[date] = []
    current = admission + timedelta(days=10)
    while len(result) < limit:
        if discharge_date is not None and current >= discharge_date:
            break
        adjusted = next_working_day(current, used=result)
        if discharge_date is not None and adjusted >= discharge_date:
            break
        result.append(adjusted)
        current += timedelta(days=10)
    return tuple(result)


def _signature_person_name(value: object) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    return re.sub(
        r"(?i)^\s*(?:лечащий\s+врач|врач(?:-психиатр)?|заведующ(?:ий|ая)\s+отделением|зав\.?\s*отделением|зав\.?\s*отд\.?)\s*[:—–-]?\s*",
        "",
        text,
    ).strip()


def dynamic_epicrisis_signature_lines(
    treating_physician: object = "",
    department_head: object = "",
) -> tuple[str, str]:
    doctor = _signature_person_name(treating_physician) or "____________________"
    head = _signature_person_name(department_head) or "____________________"
    return (f"Лечащий врач {doctor}", f"Зав.отделением {head}")


def build_dynamic_epicrisis_text(data: DynamicEpicrisisInput) -> str:
    correction = str(data.treatment_correction or "").strip() or "Лекарства принимает согласно назначениям."
    return "\n".join(
        [
            "Динамический эпикриз.",
            f"ФИО: {data.patient_name or 'не указано'}.",
            f"Дата рождения: {data.birth_date or 'не указана'}.",
            f"Лечится с: {data.sick_leave_from or 'не указано'}.",
            f"Жалобы: {data.complaints or 'без существенной динамики'}.",
            f"Принимает: {data.treatment or 'согласно листу назначений'}.",
            f"Психический статус: {data.profile_status or 'без существенной динамики'}.",
            correction,
            "Продолжение лечения по листу нетрудоспособности.",
            *dynamic_epicrisis_signature_lines(data.treating_physician, data.department_head),
        ]
    )


def _leading_date(text: str) -> date | None:
    match = _LEADING_DATE_RE.match(str(text or ""))
    if not match:
        return None
    year = int(match.group(3))
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return date(year, int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _insert_dynamic_block(doc: Document, item_date: date, lines: tuple[str, ...]) -> None:
    """Insert after all regular blocks on the same date and before later dates."""
    anchor = None
    for paragraph in doc.paragraphs:
        paragraph_date = _leading_date(paragraph.text)
        if paragraph_date is not None and paragraph_date > item_date:
            anchor = paragraph
            break

    rendered = (f"{item_date:%d.%m.%y} {lines[0]}".rstrip(), *lines[1:])
    if anchor is None:
        if doc.paragraphs:
            doc.add_paragraph("")
        for line in rendered:
            paragraph = doc.add_paragraph(line)
            if line.startswith("Лечащий врач ") or line.startswith("Зав.отделением "):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return

    for line in rendered:
        paragraph = anchor.insert_paragraph_before(line)
        if line.startswith("Лечащий врач ") or line.startswith("Зав.отделением "):
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    anchor.insert_paragraph_before("")


def apply_sick_leave_dynamic_epicrises(
    path: str | Path,
    *,
    admission_value: str,
    discharge_value: str = "",
    sick_leave_from: str = "",
    patient_name: str = "",
    birth_date: str = "",
    complaints: str = "",
    treatment: str = "",
    profile_status: str = "",
    treatment_correction: str = "",
    treating_physician: str = "",
    department_head: str = "",
) -> int:
    """Atomically add the historical sick-leave epicrisis blocks to one DOCX."""
    target = Path(path)
    admission = parse_full_date(admission_value)
    discharge = parse_optional_discharge_date(discharge_value)
    base_date = dynamic_epicrisis_base_date(admission, sick_leave_from)
    dates = dynamic_epicrisis_dates(base_date, discharge_date=discharge, limit=12)
    if not dates:
        return 0

    data = DynamicEpicrisisInput(
        patient_name=patient_name,
        birth_date=birth_date,
        sick_leave_from=f"{base_date:%d.%m.%Y}",
        complaints=complaints,
        treatment=treatment,
        profile_status=profile_status,
        treatment_correction=treatment_correction,
        treating_physician=treating_physician,
        department_head=department_head,
    )
    lines = tuple(build_dynamic_epicrisis_text(data).splitlines())
    doc = Document(str(target))
    for item_date in dates:
        _insert_dynamic_block(doc, item_date, lines)

    staged = target.with_name(f".{target.name}.dynamic-epicrisis.tmp.docx")
    try:
        doc.save(str(staged))
        os.replace(staged, target)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass
    return len(dates)


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

    @staticmethod
    def _add_dynamic_epicrises_if_needed(
        result: DiaryBatchResult,
        *,
        sick_leave_dynamic_epicrisis: bool,
        admission_value: str,
        discharge_value: str,
        sick_leave_from: str,
        patient_name: str,
        birth_date: str,
        complaints: str,
        treatment: str,
        profile_status: str,
        treatment_correction: str,
        doctor_name: str,
        department_head_name: str,
    ) -> DiaryBatchResult:
        # The established diary generator is intentionally untouched when sick
        # leave is off. Dynamic epicrises are an additive historical layer.
        if not sick_leave_dynamic_epicrisis:
            return result

        total = 0
        for created in result.created_files:
            total += apply_sick_leave_dynamic_epicrises(
                created,
                admission_value=admission_value,
                discharge_value=discharge_value,
                sick_leave_from=sick_leave_from,
                patient_name=patient_name,
                birth_date=birth_date,
                complaints=complaints,
                treatment=treatment,
                profile_status=profile_status,
                treatment_correction=treatment_correction,
                treating_physician=doctor_name,
                department_head=department_head_name,
            )
        # Kept outside the dataclass for compatibility with existing consumers.
        result.dynamic_epicrisis_count = total
        return result

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
        sick_leave_dynamic_epicrisis: bool = False,
        sick_leave_from: str = "",
        birth_date: str = "",
        complaints: str = "",
        treatment: str = "",
        profile_status: str = "",
        treatment_correction: str = "",
    ) -> DiaryBatchResult:
        def finalize(result: DiaryBatchResult) -> DiaryBatchResult:
            return self._add_dynamic_epicrises_if_needed(
                result,
                sick_leave_dynamic_epicrisis=sick_leave_dynamic_epicrisis,
                admission_value=admission_value,
                discharge_value=discharge_value,
                sick_leave_from=sick_leave_from,
                patient_name=patient_name,
                birth_date=birth_date,
                complaints=complaints,
                treatment=treatment,
                profile_status=profile_status,
                treatment_correction=treatment_correction,
                doctor_name=doctor_name,
                department_head_name=department_head_name,
            )

        if diary_files:
            return finalize(
                create_text_diaries(
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
            return finalize(
                create_text_diaries(
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
            )
