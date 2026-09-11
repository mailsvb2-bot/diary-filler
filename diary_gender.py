"""Backward-compatible facade for shared patient-gender logic."""

from __future__ import annotations

from shared_gender import (
    GENDER_WORD_PAIRS,
    adapt_text_to_patient_gender,
    convert_text_gender,
    detect_gender_from_patient_name,
    gender_label,
)

__all__ = [
    "GENDER_WORD_PAIRS",
    "detect_gender_from_patient_name",
    "gender_label",
    "adapt_text_to_patient_gender",
    "convert_text_gender",
]
