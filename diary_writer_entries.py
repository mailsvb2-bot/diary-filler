from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.table import _Row

from diary_dates import add_month, safe_row_date
from diary_table import (
    cell_int,
    fill_diary_text_cell,
    fill_text_cell,
    hospitalization_day_int,
    find_day_column,
    find_diary_column,
    find_hospitalization_day_column,
    find_month_year_column,
    is_data_row,
    is_holiday_skip_date,
)

DiaryEntry = tuple[object, int, int | None, int | None, int | None]
DatedEntry = dict[str, object]


def ensure_daily_hospitalization_rows(
    doc: Any,
    *,
    admission_date_value: date | None,
    discharge_date: date | None,
) -> int:
    """Materialize one diary row for every calendar day after admission through discharge.

    Numbered templates can contain only milestone rows (for example hospital days
    2, 3, 4, 7, 11...).  Those rows are useful as formatting/special-round
    templates, but they must not limit the calendar coverage of the generated
    diary. Existing milestone rows are preserved; missing days are cloned from a
    plain physician-signature row and inserted in order.
    """
    if admission_date_value is None or discharge_date is None:
        return 0
    if discharge_date <= admission_date_value:
        return 0

    last_hospitalization_day = (discharge_date - admission_date_value).days + 1
    inserted = 0

    for table in doc.tables:
        diary_col = find_diary_column(table)
        day_col = find_day_column(table)
        month_year_col = find_month_year_column(table)
        hospitalization_day_col = find_hospitalization_day_column(table)
        if diary_col is None or hospitalization_day_col is None:
            continue

        existing: dict[int, object] = {}
        data_rows: list[object] = []
        for row in table.rows:
            if not is_data_row(row, day_col, hospitalization_day_col):
                continue
            if len(row.cells) <= max(diary_col, hospitalization_day_col):
                continue
            hospitalization_day = hospitalization_day_int(row.cells[hospitalization_day_col].text)
            if hospitalization_day is None:
                continue
            data_rows.append(row)
            existing.setdefault(hospitalization_day, row)

        if not existing:
            continue

        # Clone an ordinary diary row, not a joint-round/department-head row.
        prototype = data_rows[0]
        for candidate in data_rows:
            diary_text = candidate.cells[diary_col].text.lower().replace("ё", "е")
            if "совместн" not in diary_text and "зав.отдел" not in diary_text and "зав отдел" not in diary_text:
                prototype = candidate
                break

        anchor = None
        for hospitalization_day in range(2, last_hospitalization_day + 1):
            existing_row = existing.get(hospitalization_day)
            if existing_row is not None:
                anchor = existing_row
                continue

            new_tr = deepcopy(prototype._tr)
            if anchor is not None:
                anchor._tr.addnext(new_tr)
            else:
                following_days = [day for day in existing if day > hospitalization_day]
                if following_days:
                    existing[min(following_days)]._tr.addprevious(new_tr)
                else:
                    table._tbl.append(new_tr)

            new_row = _Row(new_tr, table)
            fill_text_cell(
                new_row.cells[hospitalization_day_col],
                str(hospitalization_day),
                alignment=WD_ALIGN_PARAGRAPH.CENTER,
            )
            row_date = admission_date_value + timedelta(days=hospitalization_day - 1)
            if day_col is not None and len(new_row.cells) > day_col:
                fill_text_cell(new_row.cells[day_col], f"{row_date.day:02d}", alignment=WD_ALIGN_PARAGRAPH.CENTER)
            if month_year_col is not None and len(new_row.cells) > month_year_col:
                fill_text_cell(
                    new_row.cells[month_year_col],
                    f"{row_date.month:02d}.{row_date.year:04d}",
                    alignment=WD_ALIGN_PARAGRAPH.CENTER,
                )
            fill_diary_text_cell(new_row.cells[diary_col], "", keep_signature=True)

            existing[hospitalization_day] = new_row
            anchor = new_row
            inserted += 1

    return inserted


def collect_data_entries(doc: Any) -> list[DiaryEntry]:
    entries: list[DiaryEntry] = []
    for table in doc.tables:
        diary_col = find_diary_column(table)
        day_col = find_day_column(table)
        month_year_col = find_month_year_column(table)
        hospitalization_day_col = find_hospitalization_day_column(table)
        if diary_col is None:
            continue
        for row in table.rows:
            if not is_data_row(row, day_col, hospitalization_day_col):
                continue
            if len(row.cells) <= diary_col:
                continue
            entries.append((row, diary_col, day_col, month_year_col, hospitalization_day_col))
    return entries


def build_dated_entries(
    data_entries: list[DiaryEntry],
    *,
    start_month: int,
    start_year: int,
    admission_date_value: date | None,
) -> list[DatedEntry]:
    dated_entries: list[DatedEntry] = []
    current_month = start_month
    current_year = start_year
    previous_day: int | None = None

    for row, _diary_col, day_col, _month_year_col, hospitalization_day_col in data_entries:
        day_value: int | None = None
        if day_col is not None and len(row.cells) > day_col:
            day_value = cell_int(row.cells[day_col].text)

        hospitalization_day_value: int | None = None
        if hospitalization_day_col is not None and len(row.cells) > hospitalization_day_col:
            hospitalization_day_value = hospitalization_day_int(row.cells[hospitalization_day_col].text)

        if admission_date_value is not None and hospitalization_day_value is not None:
            row_date = admission_date_value + timedelta(days=max(0, hospitalization_day_value - 1))
            day_value = row_date.day
            current_month = row_date.month
            current_year = row_date.year
            previous_day = day_value
        else:
            if day_value is not None and previous_day is not None and day_value < previous_day:
                current_month, current_year = add_month(current_month, current_year, 1)
            if day_value is not None:
                previous_day = day_value
            row_date = safe_row_date(current_year, current_month, day_value)

        dated_entries.append(
            {
                "month": current_month,
                "year": current_year,
                "day": day_value,
                "date": row_date,
                "after_discharge": False,
                "skip_holiday": False,
                "skip_after_discharge": False,
            }
        )
    return dated_entries


def find_final_entry_index(
    data_entries: list[DiaryEntry],
    dated_entries: list[DatedEntry],
    *,
    discharge_date: date | None,
    remove_holiday_rows: bool,
) -> int | None:
    if discharge_date is not None:
        for entry_index in range(len(data_entries) - 1, -1, -1):
            row_date = dated_entries[entry_index]["date"]
            if isinstance(row_date, date) and row_date <= discharge_date:
                return entry_index
        if data_entries:
            raise ValueError(
                "В выбранной таблице не найдено ни одной строки до даты выписки. "
                "Проверьте месяц/год поступления и дату выписки."
            )
        return None

    for entry_index in range(len(data_entries) - 1, -1, -1):
        day_value = dated_entries[entry_index]["day"]
        row_month = int(dated_entries[entry_index]["month"])
        if not (remove_holiday_rows and is_holiday_skip_date(day_value if isinstance(day_value, int) else None, row_month)):
            return entry_index
    return None


def mark_skip_flags(
    dated_entries: list[DatedEntry],
    *,
    final_entry_index: int | None,
    discharge_date: date | None,
    remove_holiday_rows: bool,
) -> None:
    for entry_index, entry in enumerate(dated_entries):
        day_value = entry["day"]
        row_month = int(entry["month"])
        is_final_row = final_entry_index is not None and entry_index == final_entry_index
        after_final_discharge_row = (
            discharge_date is not None
            and final_entry_index is not None
            and entry_index > final_entry_index
        )
        entry["after_discharge"] = after_final_discharge_row
        entry["skip_after_discharge"] = after_final_discharge_row
        entry["skip_holiday"] = (
            remove_holiday_rows
            and is_holiday_skip_date(day_value if isinstance(day_value, int) else None, row_month)
            and not is_final_row
            and not after_final_discharge_row
        )
