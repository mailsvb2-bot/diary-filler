"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import re
from typing import Sequence

DASHES = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    for src, dst in DASHES.items():
        text = text.replace(src, dst)
    text = text.replace("\xa0", " ")
    text = text.replace("\v", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_match(text: str) -> str:
    text = normalize_text(text).lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_value(text: str) -> str:
    text = normalize_text(text)
    text = text.strip(" \t:-—–,;")
    text = re.sub(r"^сюда\s+подстав(?:лять|ляется).*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^нужно\s*/\s*не\s*нужно$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(состоит\s*/\s*не\s*состоит)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(нужен\s*/\s*не\s*нужен)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(нужно\s*/\s*не\s*нужно)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(да\s*/\s*нет)\s*[:.-]?\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def looks_like_label(value: str) -> bool:
    value = normalize_match(value)
    if not value:
        return False
    known = [
        "год рождения",
        "дата рождения",
        "зарегистрирован",
        "проживает",
        "на учете",
        "работает",
        "место работы",
        "должность",
        "больничный лист",
        "оформление инвалидности",
        "направление от рвк",
        "в 3 отделение",
        "жалобы",
        "анамнез",
        "психический статус",
        "соматический статус",
        "сомато-неврологический статус",
        "план обследования",
        "план лечения",
        "на основании",
        "диагноз",
        "эпидемиологический",
        "врач",
        "зав",
    ]
    return any(value.startswith(k) for k in known)

DIAGNOSIS_STOP_MARKERS: Sequence[str] = (
    "Дата, время", "История болезни №", "Ф.И.О.", "ФИО", "Год рождения", "Дата рождения",
    "Зарегистрирован", "Проживает", "Место жительства", "Адрес", "Работает", "Место работы",
    "Должность", "Больничный лист", "Оформление инвалидности", "Направление от РВК",
    "В 3 отделение КДП поступает", "Жалобы на момент осмотра", "Жалобы при поступлении", "Жалобы",
    "Анамнез жизни", "Анамнез заболевания", "Психический статус при поступлении", "Психический статус",
    "Соматический статус", "Сомато-неврологический статус", "План обследования", "План лечения", "Назначенное лечение",
    "Диагноз", "Назначенное лечение", "Лечение", "Эпидемиологический анамнез", "Результаты обследований", "Результаты исследований",
    "ЭЭГ", "ЭПИ", "За время лечения", "Рекомендовано", "Экспертный анамнез",
    "Врач психиатр", "Врач-психиатр", "Лечащий врач", "Зав. отделением", "Зав.отделением",
    "Зав. отд.", "Зав отд", "Зам глав врача", "Зам. гл. врача",
)
