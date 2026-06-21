from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from diary_dates import add_month, safe_row_date
from diary_table import (
    cell_int,
    find_day_column,
    find_diary_column,
    find_hospitalization_day_column,
    find_month_year_column,
    is_data_row,
    is_holiday_skip_date,
)

DiaryEntry = tuple[object, int, int | None, int | None, int | None]
DatedEntry = dict[str, object]


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
            hospitalization_day_value = cell_int(row.cells[hospitalization_day_col].text)

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
