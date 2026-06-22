"""Facade for diary table utilities."""
from __future__ import annotations

from diary_table_dates import detect_first_month_year_from_docx
from diary_table_numbers import cell_int, is_holiday_skip_date, should_remove_holiday
from diary_table_columns import is_data_row, find_column_by_header, find_diary_column, find_day_column, find_hospitalization_day_column, find_month_year_column
from diary_table_cells import clear_paragraph_keep_properties, reset_cell_to_one_paragraph, is_structural_diary_prefix, first_signature_paragraph_index, add_run_with_size, fill_text_cell, write_diary_text_into_existing_paragraph
from diary_table_text_fill import fill_diary_text_cell
from diary_table_rows import remove_row, collect_dated_entries

__all__ = ['detect_first_month_year_from_docx', 'cell_int', 'is_holiday_skip_date', 'should_remove_holiday', 'is_data_row', 'find_column_by_header', 'find_diary_column', 'find_day_column', 'find_hospitalization_day_column', 'find_month_year_column', 'clear_paragraph_keep_properties', 'reset_cell_to_one_paragraph', 'is_structural_diary_prefix', 'first_signature_paragraph_index', 'add_run_with_size', 'fill_text_cell', 'write_diary_text_into_existing_paragraph', 'fill_diary_text_cell', 'remove_row', 'collect_dated_entries']
