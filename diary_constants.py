"""Constants and regular expressions for diary filling."""

from __future__ import annotations

import re

from shared_gender import GENDER_WORD_PAIRS


MIN_STATUS_LEN = 25
STATUS_FONT_SIZE_PT = 8
DIARY_JOINT_HEAD_EXAM_TITLE = "Совместный осмотр с зав. отделением"
DIARY_TREATING_DOCTOR_SIGNATURE = "Лечащий врач Балаганин С.В."
DIARY_DEPARTMENT_HEAD_SIGNATURE = "Зав.отделением Можарова Е.А."
HOLIDAY_SKIP_MONTHS = {1, 5}
HOLIDAY_SKIP_START_DAY = 1
HOLIDAY_SKIP_END_DAY = 9
SIGNATURE_MARKERS = (
    "лечащий врач",
    "зав.отделением",
    "зав. отделением",
    "зав отделением",
    "заведующий отделением",
    "заведующая отделением",
)
STRUCTURAL_DIARY_PREFIXES = (
    "совместный осмотр",
)

DATE_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*(?:г\.?|год)?"
    r"|\d{1,2}\s+[а-яё]+\s+\d{2,4}\s*(?:г\.?|год)?"
    r")\s*",
    re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
MONTH_YEAR_RE = re.compile(r"^\s*(\d{1,2})\s*[./-]\s*(\d{4})\s*$")
FULL_DATE_RE = re.compile(r"^\s*(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\s*$")
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

STATUS_LABEL_PREFIX_RE = re.compile(
    r"^\s*(?:дата|число|номер|№|n|no\.?|запись|дневник)"
    r"\s*(?:№?\s*\d{1,6})?\s*[:.\-–—]\s*",
    re.IGNORECASE,
)
STATUS_NUMBER_BEFORE_DATE_RE = re.compile(
    r"^\s*\d{1,6}\s+(?=(?:\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}[./-]\d{1,2}|\d{1,2}\s+[а-яё]+))",
    re.IGNORECASE,
)
STATUS_NUMBER_PREFIX_RE = re.compile(r"^\s*(?:№\s*)?\d{1,6}\s*(?:[.)\-–—:]|\])\s*")
STATUS_DATE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:дата|число|от)\s*[:№.\-–—]?\s*)?"
    r"(?:"
    r"\d{4}[./-]\d{1,2}[./-]\d{1,2}"
    r"|\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?"
    r"|\d{1,2}\s+[а-яё]+\s+\d{2,4}"
    r")"
    r"\s*(?:г\.?|год)?\s*(?:\d{1,2}:\d{2})?\s*(?:[.)\]}\-–—:,;]+)?\s*",
    re.IGNORECASE,
)
STATUS_STANDALONE_DAY_PREFIX_RE = re.compile(r"^\s*\d{1,3}\s+(?=[А-ЯЁA-Z])")

EXAMINEE_FORMS_PATTERN = r"испытуем(?:ый|ая|ое|ые|ого|ой|ую|ому|ым|ыми|ых|уюся)?"
EXAMINEE_STANDARD_STATE_RE = re.compile(
    rf"(?<![A-Za-zА-ЯЁа-яё])(состояние)\s+{EXAMINEE_FORMS_PATTERN}(?![A-Za-zА-ЯЁа-яё])",
    re.IGNORECASE,
)
EXAMINEE_START_RE = re.compile(
    rf"^\s*(?<![A-Za-zА-ЯЁа-яё]){EXAMINEE_FORMS_PATTERN}(?![A-Za-zА-ЯЁа-яё])"
    r"\s*(?:[:,.;!\-–—]+)?\s*",
    re.IGNORECASE,
)
EXAMINEE_ANY_RE = re.compile(
    rf"(?<![A-Za-zА-ЯЁа-яё]){EXAMINEE_FORMS_PATTERN}(?![A-Za-zА-ЯЁа-яё])",
    re.IGNORECASE,
)

FINAL_DIARY_TEXT = (
    "Состояние улучшилось. Жалоб не предъявляет. Острой психотической симптоматики не продуцирует. "
    "Фон настроения ровный, суицидальных мыслей не высказывает. Критика к состоянию присутствует. "
    "На текущую дату оформлена выписка из стационара. Даны рекомендации"
)
