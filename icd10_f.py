"""Facade for the local ICD-10 F00-F99 directory."""
from __future__ import annotations

from icd10_models import ICD10Diagnosis
from icd10_f_data import ICD10_F_DIAGNOSES, _BASE_ROWS, _SUBSTANCE_STATES, _SUBSTANCE_TITLES, _build_rows, _code_sort_key, _substance_rows
from icd10_f_search import all_diagnosis_display_values, format_diagnosis, normalize_query, search_icd10_f, _digits_only

__all__ = [
    "ICD10Diagnosis",
    "ICD10_F_DIAGNOSES",
    "format_diagnosis",
    "normalize_query",
    "search_icd10_f",
    "all_diagnosis_display_values",
    "_BASE_ROWS",
    "_SUBSTANCE_STATES",
    "_SUBSTANCE_TITLES",
    "_build_rows",
    "_code_sort_key",
    "_substance_rows",
    "_digits_only",
]
