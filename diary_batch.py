"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Sequence

from docx import Document

from diary_dates import parse_admission_month_year, parse_full_date, parse_optional_discharge_date
from diary_constants import FINAL_DIARY_TEXT
from shared_gender import adapt_text_to_patient_gender, detect_gender_from_patient_name
from diary_models import DiaryBatchResult
from diary_paths import available_path, make_diary_output_name, safe_filename_part
from diary_table import (
    cell_int,
    detect_first_month_year_from_docx,
    find_day_column,
    find_hospitalization_day_column,
    find_month_year_column,
    hospitalization_day_int,
)
from diary_text_parser import clean_status_text, extract_statuses_from_docx, is_signature_paragraph_text, remove_examinee_words
from diary_writer import fill_diary_file

def _existing_docx_files(paths: Iterable[str | Path], label: str) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        if raw_path is None or str(raw_path).strip() == "":
            raise ValueError(f"Пустой путь к файлу ({label}).")
        path = Path(raw_path).expanduser()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Не найден файл ({label}): {path}")
        if path.suffix.lower() not in {".docx", ".docm"}:
            raise ValueError(f"Неверный формат файла ({label}): {path.suffix or 'без расширения'}. Разрешено: .docx, .docm.")
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _resolve_output_dir(output_dir: str | Path | None, fallback_dir: Path) -> Path:
    if output_dir is None or str(output_dir).strip() == "":
        result = fallback_dir
    else:
        result = Path(output_dir).expanduser()
    if result.exists() and not result.is_dir():
        raise ValueError(f"Папка результата указывает на файл, а не на папку: {result}")
    result.mkdir(parents=True, exist_ok=True)
    return result


def read_statuses_from_files(
    paths: Iterable[str | Path],
    *,
    preserve_duplicates: bool = False,
) -> list[str]:
    statuses: list[str] = []
    seen: set[str] = set()
    for path in _existing_docx_files(paths, "тексты дневников"):
        for status in extract_statuses_from_docx(path, deduplicate=not preserve_duplicates):
            status = status.strip()
            key = " ".join(status.lower().replace("ё", "е").split())
            if preserve_duplicates or key not in seen:
                statuses.append(status)
                seen.add(key)
    return statuses


def open_folder(path: str | Path) -> bool:
    folder = Path(path).expanduser()
    try:
        if os.environ.get("CI") or not folder.exists() or not folder.is_dir():
            return False
        folder_text = str(folder)
        if sys.platform.startswith("win"):
            os.startfile(folder_text)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder_text], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        else:
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                return False
            subprocess.Popen(["xdg-open", folder_text], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        return True
    except Exception:
        return False




def _two_digit_year(year: int) -> int:
    return year + (2000 if year < 70 else 1900) if year < 100 else year


def _full_dates_in_text(text: str) -> list[date]:
    result: list[date] = []
    for match in re.finditer(r"(?<!\d)([0-3]?\d)[./-]([01]?\d)[./-](20\d{2}|\d{2})(?!\d)", text or ""):
        try:
            result.append(date(_two_digit_year(int(match.group(3))), int(match.group(2)), int(match.group(1))))
        except ValueError:
            continue
    return result


def _text_diary_dates_from_sources(
    paths: Sequence[Path],
    *,
    admission_date_value: date,
    discharge_date_value: date | None,
) -> tuple[date, ...]:
    """Read the doctor-selected «Даты» source without copying its table layout.

    Prefer explicit calendar dates. Legacy 01-31 templates that only contain a
    hospitalization-day column remain supported: day 2 means admission + 1 day.
    This preserves the user's date plan while the generated document itself is
    text-only, matching the proven Dokkomplekt diary route.
    """
    explicit: set[date] = set()
    hospitalization_offsets: set[int] = set()

    def accept(candidate: date) -> None:
        if candidate <= admission_date_value:
            return
        if discharge_date_value is not None and candidate > discharge_date_value:
            return
        explicit.add(candidate)

    for path in paths:
        doc = Document(str(path))
        for paragraph in doc.paragraphs:
            for candidate in _full_dates_in_text(paragraph.text):
                accept(candidate)
        for table in doc.tables:
            day_col = find_day_column(table)
            month_year_col = find_month_year_column(table)
            hospitalization_col = find_hospitalization_day_column(table)
            for row in table.rows:
                if hospitalization_col is not None and len(row.cells) > hospitalization_col:
                    hospital_day = hospitalization_day_int(row.cells[hospitalization_col].text)
                    if hospital_day is not None and hospital_day >= 2:
                        hospitalization_offsets.add(hospital_day - 1)

                if day_col is None or month_year_col is None:
                    continue
                if len(row.cells) <= max(day_col, month_year_col):
                    continue
                day_value = cell_int(row.cells[day_col].text)
                month_year = re.fullmatch(
                    r"\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\s*",
                    row.cells[month_year_col].text or "",
                )
                if day_value is None or month_year is None:
                    continue
                try:
                    candidate = date(
                        _two_digit_year(int(month_year.group(2))),
                        int(month_year.group(1)),
                        int(day_value),
                    )
                except ValueError:
                    continue
                accept(candidate)

    if explicit:
        source_dates = tuple(sorted(explicit))
    else:
        fallback_dates: list[date] = []
        for offset in sorted(hospitalization_offsets):
            candidate = admission_date_value + timedelta(days=offset)
            if discharge_date_value is not None and candidate > discharge_date_value:
                continue
            fallback_dates.append(candidate)
        source_dates = tuple(fallback_dates)

    # Dokkomplekt_Universal medical diary contract: the normal clinical
    # calendar is D0+1, D0+2, D0+3, D0+7, then twice weekly by alternating
    # +3/+4 day steps.  Numbered 01-31 «Даты» files are compatibility/source
    # material (including signatures), not a command to write every day.
    # The discharge date is added separately as the single final diary entry.
    if source_dates and discharge_date_value is not None and discharge_date_value > admission_date_value:
        max_offset = (discharge_date_value - admission_date_value).days
        return tuple(
            admission_date_value + timedelta(days=offset)
            for offset in _clinical_diary_offsets(max_offset)
        )
    return source_dates


def _clinical_diary_offsets(max_offset: int) -> tuple[int, ...]:
    """Return the proven Dokkomplekt clinical diary day offsets.

    D0+1, D0+2, D0+3, D0+7, then twice weekly by alternating +3/+4
    day steps.  The discharge entry is handled separately by the text diary
    builder, so this function only plans regular clinical diary dates.
    """
    if max_offset < 1:
        return ()
    offsets = [1, 2, 3, 7]
    current = 7
    add_three = True
    while current < max_offset:
        current += 3 if add_three else 4
        add_three = not add_three
        if current <= max_offset:
            offsets.append(current)
    return tuple(offset for offset in offsets if offset <= max_offset)


def _signature_lines_from_diary_sources(paths: Sequence[Path]) -> tuple[str, ...]:
    """Preserve doctor-owned signature wording when converting a table to text."""
    found: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        for line in str(text or "").splitlines():
            value = " ".join(line.split()).strip()
            key = value.lower().replace("ё", "е")
            if value and is_signature_paragraph_text(value) and key not in seen:
                seen.add(key)
                found.append(value)

    for path in paths:
        doc = Document(str(path))
        for paragraph in doc.paragraphs:
            add(paragraph.text)
        for table in doc.tables:
            for row in table.rows:
                # python-docx may expose the same merged physical cell several
                # times inside one row. Deduplicate only within that row: lxml
                # wrappers from earlier rows may be released and Python can
                # reuse their object ids, which previously made later signature
                # cells (notably «Зав.отделением») disappear from the scan.
                seen_cells: set[int] = set()
                for cell in row.cells:
                    cell_id = id(cell._tc)
                    if cell_id in seen_cells:
                        continue
                    seen_cells.add(cell_id)
                    for paragraph in cell.paragraphs:
                        add(paragraph.text)
    if len(found) >= 2:
        return tuple(found[:2])
    if len(found) == 1:
        only = found[0]
        key = only.lower().replace("ё", "е")
        # The text-diary contract always has two signature roles. Preserve the
        # doctor-owned wording we did find, but never invent a missing person's
        # name: supplement only the blank role line required for signing.
        if ("зав" in key or "завед" in key) and "отдел" in key:
            return ("Лечащий врач ____________________", only)
        return (only, "Зав. отделением ____________________")
    return ("Лечащий врач ____________________", "Зав. отделением ____________________")


def _build_text_diary_entries(
    statuses: Sequence[str],
    dates: Sequence[date],
    *,
    discharge_date_value: date | None,
    force_final_diary: bool,
    repeat_statuses: bool,
    patient_gender: str | None,
) -> tuple[list[tuple[date, str]], int, int]:
    planned = tuple(sorted(dict.fromkeys(dates)))
    final_date: date | None = None
    if force_final_diary:
        if discharge_date_value is not None:
            final_date = discharge_date_value
            planned = tuple(item for item in planned if item < final_date)
        elif planned:
            final_date = planned[-1]
            planned = planned[:-1]

    entries: list[tuple[date, str]] = []
    status_index = 0
    gender_replacements = 0
    for item_date in planned:
        if not statuses:
            break
        if status_index >= len(statuses):
            if not repeat_statuses:
                break
            status_index = 0
        status = statuses[status_index]
        status_index += 1
        adapted, changed = adapt_text_to_patient_gender(status, patient_gender)
        gender_replacements += changed
        cleaned = remove_examinee_words(clean_status_text(adapted))
        entries.append((item_date, cleaned))

    final_rows = 0
    if final_date is not None:
        adapted, changed = adapt_text_to_patient_gender(FINAL_DIARY_TEXT, patient_gender)
        gender_replacements += changed
        entries.append((final_date, remove_examinee_words(clean_status_text(adapted))))
        final_rows = 1
    return entries, final_rows, gender_replacements


def _write_text_diary_docx(path: Path, entries: Sequence[tuple[date, str]], signatures: Sequence[str]) -> None:
    doc = Document()
    for item_date, text in entries:
        if doc.paragraphs:
            doc.add_paragraph("")
        entry_paragraph = doc.add_paragraph(f"{item_date:%d.%m.%y} {text}".rstrip())
        # Keep one clinical diary block together in Word/PDF. Without these
        # flags the final department-head signature can become an orphan on a
        # separate page even though the diary itself still fits on the previous
        # page. Chaining keep-with-next through the first signature keeps the
        # diary + signature block visually atomic.
        entry_paragraph.paragraph_format.keep_together = True
        if signatures:
            entry_paragraph.paragraph_format.keep_with_next = True
        for index, signature in enumerate(signatures):
            signature_paragraph = doc.add_paragraph(signature)
            if index < len(signatures) - 1:
                signature_paragraph.paragraph_format.keep_with_next = True
    doc.save(str(path))


def _fill_text_diary_batch(
    *,
    diary_file_paths: Sequence[Path],
    statuses: Sequence[str],
    result_dir: Path,
    patient_filename: str,
    admission_date_value: date | None,
    discharge_date_value: date | None,
    repeat_statuses: bool,
    force_final_diary: bool,
    patient_gender: str | None,
    write_report: bool,
    admission_value: str,
    discharge_value: str,
) -> DiaryBatchResult:
    if admission_date_value is None:
        raise ValueError("Для текстовых дневников нужна полная дата поступления.")
    dates = _text_diary_dates_from_sources(
        diary_file_paths,
        admission_date_value=admission_date_value,
        discharge_date_value=discharge_date_value,
    )
    same_day_final = bool(
        force_final_diary
        and discharge_date_value is not None
        and discharge_date_value == admission_date_value
    )
    if not dates and not same_day_final:
        raise ValueError(
            "В выбранном источнике «Даты» не найдено дат дневников после поступления. "
            "Проверьте файл 01–31 или выберите другой источник дат."
        )
    signatures = _signature_lines_from_diary_sources(diary_file_paths)
    entries, final_rows, gender_replacements = _build_text_diary_entries(
        statuses,
        dates,
        discharge_date_value=discharge_date_value,
        force_final_diary=force_final_diary,
        repeat_statuses=repeat_statuses,
        patient_gender=patient_gender,
    )
    if not entries:
        raise ValueError("Не удалось сформировать ни одной записи дневника по выбранным датам и текстам.")

    created_files: list[Path] = []
    report_path: Path | None = None
    out_name = make_diary_output_name(patient_filename, file_index=1, total_files=1)
    report_name = "ОТЧЁТ_дневники.txt"
    with TemporaryDirectory(prefix=".diary-autofill-", dir=str(result_dir)) as tmp_dir:
        tmp_root = Path(tmp_dir)
        staged_doc = tmp_root / "diary.docx"
        _write_text_diary_docx(staged_doc, entries, signatures)
        staged_report: Path | None = None
        if write_report:
            staged_report = tmp_root / report_name
            staged_report.write_text(
                "\n".join(
                    [
                        "ОТЧЁТ: текстовые дневники",
                        f"Дата запуска: {datetime.now():%d.%m.%Y %H:%M:%S}",
                        f"Поступление: {admission_value}",
                        f"Выписка: {discharge_value or 'не указана'}",
                        f"Дат из источника «Даты»: {len(dates)}",
                        f"Создано записей: {len(entries)}",
                        f"Финальных записей: {final_rows}",
                    ]
                ),
                encoding="utf-8",
            )
        try:
            final_path = available_path(result_dir / out_name)
            os.replace(staged_doc, final_path)
            created_files.append(final_path)
            if staged_report is not None:
                report_path = available_path(result_dir / report_name)
                os.replace(staged_report, report_path)
        except Exception:
            for output_path in reversed(created_files):
                try:
                    output_path.unlink()
                except OSError:
                    pass
            if report_path is not None:
                try:
                    report_path.unlink()
                except OSError:
                    pass
            raise

    return DiaryBatchResult(
        created_files=created_files,
        report_path=report_path,
        processed_files=1,
        filled_rows=len(entries),
        detected_rows=len(dates),
        month_cells_filled=0,
        final_rows_filled=final_rows,
        gender_replacements=gender_replacements,
        removed_holiday_rows=0,
        removed_after_discharge_rows=0,
    )


def create_text_diaries(
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
    """Production text-diary entry point.

    This API intentionally exposes only options that affect the paragraph-based
    production route. Legacy table-fill switches remain on ``fill_diary_batch``
    for backward compatibility and cannot steer the GUI into the table engine.
    """
    if not diary_files:
        raise ValueError("Сначала выберите файлы-таблицы дневников, которые нужно заполнить.")
    diary_file_paths = _existing_docx_files(diary_files, "таблица дневников")
    status_file_paths = _existing_docx_files(status_files, "тексты дневников") if status_files else []

    # Preserve the historical validation boundary before requiring a full date.
    parse_admission_month_year(admission_value)
    try:
        admission_date_value = parse_full_date(admission_value)
    except ValueError:
        admission_date_value = None
    discharge_date_value = parse_optional_discharge_date(discharge_value)
    if admission_date_value is not None and discharge_date_value is not None and discharge_date_value < admission_date_value:
        raise ValueError("Дата выписки не может быть раньше даты поступления.")

    patient_filename = safe_filename_part(patient_name)
    gender_name = safe_filename_part(gender_source_name or patient_name)
    patient_gender = detect_gender_from_patient_name(gender_name)
    statuses = read_statuses_from_files(status_file_paths, preserve_duplicates=True)
    if status_files and not statuses:
        raise ValueError("В выбранных файлах с текстами дневников не найдено подходящих текстов.")

    result_dir = _resolve_output_dir(output_dir, diary_file_paths[0].parent)
    return _fill_text_diary_batch(
        diary_file_paths=diary_file_paths,
        statuses=statuses,
        result_dir=result_dir,
        patient_filename=patient_filename,
        admission_date_value=admission_date_value,
        discharge_date_value=discharge_date_value,
        repeat_statuses=repeat_statuses,
        force_final_diary=force_final_diary,
        patient_gender=patient_gender,
        write_report=write_report,
        admission_value=admission_value,
        discharge_value=discharge_value,
    )


def fill_diary_batch(
    *,
    status_files: Sequence[str | Path],
    diary_files: Sequence[str | Path],
    output_dir: str | Path | None,
    patient_name: str,
    admission_value: str,
    gender_source_name: str | None = None,
    discharge_value: str = "",
    repeat_statuses: bool = True,
    reset_each_file: bool = True,
    keep_signature: bool = True,
    fill_months: bool = True,
    force_final_diary: bool = True,
    remove_holiday_rows: bool = False,
    open_result_folder: bool = False,
    write_report: bool = False,
    text_output: bool = False,
) -> DiaryBatchResult:
    if text_output:
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

    if not diary_files:
        raise ValueError("Сначала выберите файлы-таблицы дневников, которые нужно заполнить.")
    diary_file_paths = _existing_docx_files(diary_files, "таблица дневников")
    status_file_paths = _existing_docx_files(status_files, "тексты дневников") if status_files else []
    if not status_files and not fill_months and not force_final_diary:
        raise ValueError("Сначала выберите файл(ы) с текстами дневников, включите месяц/год или финальную запись выписки.")

    start_month, start_year = parse_admission_month_year(admission_value)
    try:
        admission_date_value = parse_full_date(admission_value)
    except ValueError:
        admission_date_value = None
    discharge_date_value = parse_optional_discharge_date(discharge_value)
    if admission_date_value is not None and discharge_date_value is not None and discharge_date_value < admission_date_value:
        raise ValueError("Дата выписки не может быть раньше даты поступления.")
    patient_filename = safe_filename_part(patient_name)
    gender_name = safe_filename_part(gender_source_name or patient_name)
    patient_gender = detect_gender_from_patient_name(gender_name)
    # Не угадываем род по неоднозначной фамилии. При None дневник создаётся с
    # исходной формулировкой текста; это безопаснее, чем молча менять мужской/
    # женский род неверно. Полный ФИО с отчеством по-прежнему определяется.

    statuses = read_statuses_from_files(status_file_paths, preserve_duplicates=False)
    if status_files and not statuses:
        raise ValueError("В выбранных файлах с текстами дневников не найдено подходящих текстов.")

    first_dir = diary_file_paths[0].parent
    result_dir = _resolve_output_dir(output_dir, first_dir)

    idx = 0
    created_files: list[Path] = []
    lines = [
        "ОТЧЁТ: заполнение дневников",
        f"Дата запуска: {datetime.now():%d.%m.%Y %H:%M:%S}",
        f"Пациент / имя файлов: {patient_filename}",
        f"ФИО для определения рода: {gender_name}",
        f"Поступление: {admission_value}",
        f"Выписка: {discharge_value or 'не указана'}",
        f"Папка результата: {result_dir}",
        f"Текстов дневников найдено: {len(statuses)}",
        "",
    ]

    total_filled = 0
    total_detected = 0
    total_months = 0
    total_final = 0
    total_gender = 0
    total_holidays = 0
    total_after_discharge = 0

    # Fill every diary in an isolated same-volume staging directory. A broken
    # template or writer error cannot leave an empty/half-filled patient DOCX.
    staged_outputs: list[tuple[Path, str]] = []
    staged_report: Path | None = None
    report_name = "ОТЧЁТ_дневники.txt"
    with TemporaryDirectory(prefix=".diary-autofill-", dir=str(result_dir)) as tmp_dir:
        tmp_root = Path(tmp_dir)
        for n, src_path in enumerate(diary_file_paths, start=1):
            out_name = make_diary_output_name(patient_filename, file_index=n, total_files=len(diary_file_paths))
            staged_path = tmp_root / f"{n:02d}.docx"
            shutil.copy2(src_path, staged_path)
            effective_start_idx = 0 if reset_each_file else idx
            result = fill_diary_file(
                staged_path,
                statuses,
                start_idx=effective_start_idx,
                repeat_statuses=repeat_statuses,
                keep_signature=keep_signature,
                fill_months=fill_months,
                start_month=start_month,
                start_year=start_year,
                admission_date_value=admission_date_value,
                discharge_date=discharge_date_value,
                force_final_diary=force_final_diary,
                remove_holiday_rows=remove_holiday_rows,
                patient_gender=patient_gender,
            )
            if not reset_each_file:
                idx = result.next_status_index
            staged_outputs.append((staged_path, out_name))
            total_filled += result.filled_rows
            total_detected += result.detected_rows
            total_months += result.month_cells_filled
            total_final += result.final_rows_filled
            total_gender += result.gender_replacements
            total_holidays += result.removed_holiday_rows
            total_after_discharge += result.removed_after_discharge_rows
            lines.append(
                f"{src_path.name}: строк найдено {result.detected_rows}; дневников заполнено {result.filled_rows}; "
                f"месяц/год {result.month_cells_filled}; финальных записей {result.final_rows_filled}; "
                f"замен пола {result.gender_replacements}; удалено праздников {result.removed_holiday_rows}; "
                f"удалено после выписки {result.removed_after_discharge_rows}"
            )

        lines.extend(
            [
                "",
                f"Файлов обработано: {len(staged_outputs)}/{len(diary_file_paths)}",
                f"Дневников заполнено: {total_filled}",
                f"Строк дневников найдено: {total_detected}",
                f"Дат месяц/год заполнено: {total_months}",
                f"Финальных записей: {total_final}",
                f"Грамматических замен по полу: {total_gender}",
                f"Удалено праздничных строк: {total_holidays}",
                f"Удалено строк после выписки: {total_after_discharge}",
            ]
        )
        if write_report:
            staged_report = tmp_root / report_name
            staged_report.write_text("\n".join(lines), encoding="utf-8")

        report_path: Path | None = None
        try:
            for staged_path, out_name in staged_outputs:
                final_path = available_path(result_dir / out_name)
                os.replace(staged_path, final_path)
                created_files.append(final_path)
            if staged_report is not None:
                report_path = available_path(result_dir / report_name)
                os.replace(staged_report, report_path)
        except Exception:
            for output_path in reversed(created_files):
                try:
                    output_path.unlink()
                except OSError:
                    pass
            if report_path is not None:
                try:
                    report_path.unlink()
                except OSError:
                    pass
            raise

    if open_result_folder:
        open_folder(result_dir)

    return DiaryBatchResult(
        created_files=created_files,
        report_path=report_path,
        processed_files=len(created_files),
        filled_rows=total_filled,
        detected_rows=total_detected,
        month_cells_filled=total_months,
        final_rows_filled=total_final,
        gender_replacements=total_gender,
        removed_holiday_rows=total_holidays,
        removed_after_discharge_rows=total_after_discharge,
    )
