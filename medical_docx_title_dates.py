"""Facade for title/admission date extraction from DOCX files."""
from __future__ import annotations

from medical_docx_date_patterns import _TITLE_DATE_RE, _first_valid_full_date, _normalize_full_date_match
from medical_docx_title_context import (
    _date_match_has_birth_context,
    _is_birth_or_demographic_context,
    _is_primary_title_context,
    _is_strong_birth_date_context,
)
from medical_docx_title_finder import _admission_date_from_filename, _best_title_date_in_text, extract_admission_date_from_title_docx
from medical_docx_xml_fragments import _docx_xml_text_fragments

__all__ = [
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
    "extract_admission_date_from_title_docx",
]
