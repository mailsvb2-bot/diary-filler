"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import re

from diary_constants import GENDER_WORD_PAIRS
from diary_text_parser import normalize_text

def _name_token(value: str) -> str:
    return re.sub(r"[^A-Za-zА-Яа-яЁё-]+", "", value).strip("-")


def detect_gender_from_patient_name(patient_name: str) -> str | None:
    """Conservatively infer Russian grammatical gender from a patient name.

    Prefer a full patronymic, then strongly gendered surname endings and only
    then an unabbreviated given name.  Indeclinable/ambiguous surnames such as
    ``Шевченко`` with initials return ``None`` instead of silently becoming
    female just because the surname ends with a vowel.
    """
    value = normalize_text(patient_name)
    if not value:
        return None
    tokens = [_name_token(part) for part in value.split()]
    tokens = [part for part in tokens if part]
    if not tokens:
        return None

    lowered = [part.lower().replace("ё", "е") for part in tokens]

    # Patronymics are the strongest signal when a full FIO is available.
    for token in lowered[1:]:
        if token.endswith(("овна", "евна", "ична", "инична")):
            return "female"
        if token.endswith(("ович", "евич", "ич")):
            return "male"

    surname = lowered[0]
    if surname.endswith(("ова", "ева", "ина", "ына", "ская", "цкая", "ая", "яя")):
        return "female"
    if surname.endswith(("ов", "ев", "ин", "ын", "ский", "цкий", "ой", "ый", "ий")):
        return "male"

    # Initials carry no gender information.  A full given name can resolve many
    # indeclinable surnames without pretending that every vowel-ending surname
    # is feminine.
    if len(lowered) >= 2 and len(lowered[1]) > 2:
        given = lowered[1]
        male_a_ya_names = {"илья", "никита", "кузьма", "фома", "лука", "данила", "савва"}
        if given in male_a_ya_names:
            return "male"
        if given.endswith(("а", "я")):
            return "female"
        if given.endswith(("й", "н", "р", "м", "л", "в", "д", "т", "с", "г", "к", "п")):
            return "male"

    return None

def gender_label(gender: str | None) -> str:
    if gender == "male":
        return "мужской"
    if gender == "female":
        return "женский"
    return "не определён"


def _preserve_case(source: str, target: str) -> str:
    if source.isupper():
        return target.upper()
    if source[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


def _replace_gender_pair(text: str, source: str, target: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?<![A-Za-zА-Яа-яЁё]){re.escape(source)}(?![A-Za-zА-Яа-яЁё])", re.IGNORECASE)
    count = 0

    def repl(match: re.Match) -> str:
        nonlocal count
        count += 1
        return _preserve_case(match.group(0), target)

    return pattern.sub(repl, text), count


def adapt_text_to_patient_gender(text: str, gender: str | None) -> tuple[str, int]:
    """Adapt known gendered diary words to the detected patient gender."""
    if gender not in {"male", "female"} or not text:
        return text, 0

    pairs = sorted(GENDER_WORD_PAIRS, key=lambda pair: max(len(pair[0]), len(pair[1])), reverse=True)
    result = text
    replacements = 0
    for male, female in pairs:
        source, target = (female, male) if gender == "male" else (male, female)
        result, changed = _replace_gender_pair(result, source, target)
        replacements += changed
    return result, replacements


def convert_text_gender(text: str, gender: str | None) -> tuple[str, int]:
    """Backward-compatible alias used by the combined application."""
    return adapt_text_to_patient_gender(text, gender)
