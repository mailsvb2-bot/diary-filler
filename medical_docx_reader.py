"""Facade for DOCX reading helpers."""
from __future__ import annotations

from medical_docx_blocks import extract_docx_text, iter_block_items
from medical_docx_title_dates import (
    _TITLE_DATE_RE,
    _admission_date_from_filename,
    _best_title_date_in_text,
    _date_match_has_birth_context,
    _docx_xml_text_fragments,
    _first_valid_full_date,
    _is_birth_or_demographic_context,
    _is_primary_title_context,
    _is_strong_birth_date_context,
    _normalize_full_date_match,
    extract_admission_date_from_title_docx,
)

__all__ = [
    "iter_block_items",
    "extract_docx_text",
    "extract_admission_date_from_title_docx",
    "_TITLE_DATE_RE",
    "_normalize_full_date_match",
    "_first_valid_full_date",
    "_is_primary_title_context",
    "_is_birth_or_demographic_context",
    "_is_strong_birth_date_context",
    "_date_match_has_birth_context",
    "_best_title_date_in_text",
    "_docx_xml_text_fragments",
    "_admission_date_from_filename",
]
