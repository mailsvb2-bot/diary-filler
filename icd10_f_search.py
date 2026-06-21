"""Локальный справочник МКБ-10, класс V (F00-F99).

Назначение внутри программы:
- дать врачу быстрый выбор шифра и названия диагноза в UI;
- искать по коду, цифрам кода и фрагментам русского названия;
- не требовать интернет при работе программы.

Справочник содержит базовые рубрики и наиболее употребимые подрубрики F00-F99.
"""

from __future__ import annotations

import re

from icd10_models import ICD10Diagnosis
from icd10_f_data import ICD10_F_DIAGNOSES, _code_sort_key


def format_diagnosis(item: ICD10Diagnosis) -> str:
    return item.display


def normalize_query(value: str) -> str:
    value = (value or "").strip().upper().replace(",", ".")
    value = value.replace("Ё", "Е")
    value = re.sub(r"\s+", " ", value)
    return value


def _digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value)


def search_icd10_f(query: str, *, limit: int = 80) -> list[ICD10Diagnosis]:
    """Search by code, code digits, or Russian title fragment.

    Examples:
    - "41" -> F41, F41.0, F41.1, F41.2...
    - "F41.2" -> exact code first
    - "трев" -> anxiety-related diagnoses
    """
    q = normalize_query(query)
    if not q:
        return ICD10_F_DIAGNOSES[:limit]

    q_digits = _digits_only(q)
    q_no_space = q.replace(" ", "")
    ranked: list[tuple[int, ICD10Diagnosis]] = []

    for item in ICD10_F_DIAGNOSES:
        code = item.code.upper()
        code_digits = _digits_only(code)
        text = f"{item.code} {item.title}".upper().replace("Ё", "Е")
        score: int | None = None

        if q_no_space == code:
            score = 0
        elif q_no_space and code.startswith(q_no_space):
            score = 1
        elif q_digits and code_digits.startswith(q_digits):
            score = 2
        elif q_digits and q_digits in code_digits:
            score = 3
        elif q and q in text:
            score = 4
        else:
            # Search each word independently for queries like "трев деп".
            parts = [part for part in re.split(r"\s+", q) if part]
            if parts and all(part in text for part in parts):
                score = 5

        if score is not None:
            ranked.append((score, item))

    ranked.sort(key=lambda row: (row[0], _code_sort_key(row[1].code), row[1].title))
    return [item for _score, item in ranked[:limit]]


def all_diagnosis_display_values() -> list[str]:
    return [format_diagnosis(item) for item in ICD10_F_DIAGNOSES]
