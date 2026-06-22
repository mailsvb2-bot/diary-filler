from __future__ import annotations

import re

from medical_text_utils import normalize_match
from medical_docx_date_patterns import _TITLE_DATE_RE


def _is_primary_title_context(value: str) -> bool:
    low = normalize_match(value or "")
    return any(
        marker in low
        for marker in (
            "первичный осмотр",
            "первичный",
            "направление на госпитализацию",
            "госпитализацию",
        )
    )


def _is_birth_or_demographic_context(value: str) -> bool:
    low = normalize_match(value or "")
    return any(
        marker in low
        for marker in (
            "ф.и.о",
            "фио",
            "фамилия имя отчество",
            "дата рождения",
            "год рождения",
            "г.р",
            "возраст",
            "родился",
            "родилась",
        )
    )


def _is_strong_birth_date_context(value: str) -> bool:
    """True only for fragments that explicitly describe birth/age dates.

    ФИО само по себе не запрещает строку: в реальных таблицах ФИО может
    стоять в той же строке, что и заголовок документа. Запрещаем именно
    маркеры даты рождения/возраста, чтобы дата поступления не превращалась
    в день рождения пациента.
    """
    low = normalize_match(value or "")
    return any(
        marker in low
        for marker in (
            "дата рождения",
            "год рождения",
            "г.р",
            "возраст",
            "родился",
            "родилась",
        )
    )


def _date_match_has_birth_context(text: str, match: re.Match[str]) -> bool:
    # Keep character indexes aligned with ``match``. ``normalize_match`` collapses
    # whitespace and can shift positions, which may make a birth-date marker look
    # related to the wrong date.
    low = (text or "").lower().replace("ё", "е")
    start = max(0, match.start() - 120)
    end = min(len(low), match.end() + 60)
    before = low[start:match.start()]
    after = low[match.end():end]
    birth_markers = (
        "дата рождения",
        "год рождения",
        "г.р",
        "возраст",
        "родился",
        "родилась",
    )

    # Маркер рождения перед датой запрещает её только тогда, когда между
    # маркером и этой датой нет другой даты. Пример:
    # "Дата рождения: 04.01.2000 | 12.01.2026 Первичный осмотр" —
    # маркер относится к 04.01.2000, а не к 12.01.2026.
    marker_positions = [before.rfind(marker) for marker in birth_markers]
    marker_pos = max(marker_positions) if marker_positions else -1
    if marker_pos >= 0:
        tail_after_marker = before[marker_pos:]
        if not _TITLE_DATE_RE.search(tail_after_marker):
            return True

    # Иногда пишут "04.01.2000 дата рождения".
    if any(marker in after[:45] for marker in birth_markers):
        return True

    # Компактный вариант без слов "дата рождения": ФИО + дата. Запрещаем
    # только если рядом с этой датой нет явного заголовка документа.
    if ("ф.и.о" in before[-80:] or "фио" in before[-80:] or "фамилия имя отчество" in before[-80:]) and not _is_primary_title_context((before + after)[-160:]):
        return True
    return False
