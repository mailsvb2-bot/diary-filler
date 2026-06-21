from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from medical_docx_reader import (
    extract_admission_date_from_title_docx,
    extract_docx_text,
    _first_valid_full_date,
    _is_birth_or_demographic_context,
    _is_primary_title_context,
)
from medical_models import PatientData
from medical_parser_sanitize import sanitize_diagnosis
from medical_text_utils import (
    DIAGNOSIS_STOP_MARKERS,
    clean_value,
    looks_like_label,
    normalize_match,
    normalize_text,
)


class MedicalParserInlineMixin:
    @staticmethod
    def _parsed_field_value_is_only_label(field_name: str, value: str) -> bool:
        """Safely clear accidental labels without deleting meaningful values.

        Some template cells contain only labels, and those should not be copied
        into generated documents. But broad label detection must not delete real
        values like a position ``врач`` / ``врач-психиатр``.
        """
        cleaned = clean_value(value)
        if not cleaned:
            return True
        norm = normalize_match(cleaned)
        if field_name == "position":
            return norm in {"должность", "в должности"}
        if field_name == "work_org":
            return norm in {"работает", "место работы", "работа", "организация"}
        if field_name in {"doctor", "head"}:
            return False
        return looks_like_label(cleaned)

    def _extract_inline(self, text: str, aliases: Sequence[str]) -> str:
        lines = text.splitlines()
        for alias in aliases:
            alias_re = self._inline_value_pattern(alias)
            for line in lines:
                line_norm = normalize_text(line)
                m = re.search(alias_re, line_norm, flags=re.IGNORECASE)
                if not m or self._ignore_inline_alias_match(line_norm, alias, m.start(), m.end()):
                    continue
                value = line_norm[m.end():]
                value = re.sub(r"^\s*[:№N#.-]*\s*", "", value)
                value = self._cut_at_next_inline_marker(value, aliases)
                value = clean_value(value)
                if value and not self._value_is_only_foreign_label(alias, value):
                    return value
        return ""

    @staticmethod
    def _ignore_inline_alias_match(line: str, alias: str, start: int, end: int) -> bool:
        """Reject false inline matches such as ``Не работает``.

        The alias ``Работает`` is a field label only when it introduces a value
        (``Работает: ООО...`` / ``Работает в организации: ...``). In the phrase
        ``Не работает`` it is the value itself, not a label; accepting it used to
        produce garbage like ``ет`` or an empty work organization.
        """
        alias_norm = normalize_match(alias)
        before = normalize_match(line[:start])
        after = line[end:]
        if alias_norm == "работает" and re.search(r"(?:^|\s)не$", before):
            return True
        # A bare label without a separator/value is not a field.
        if not re.match(r"\s*(?:[:№N#.-]|в\s+организации|$)", after, flags=re.IGNORECASE):
            return False
        if alias_norm == "работает" and not clean_value(after):
            return True
        return False

    @staticmethod
    def _value_is_only_foreign_label(alias: str, value: str) -> bool:
        """Return True only when a captured value is another section label.

        ``looks_like_label()`` is intentionally broad and contains words like
        ``врач``. That word is a valid position, so applying the broad check to
        every captured value erased real job titles.
        """
        cleaned = clean_value(value)
        if not cleaned:
            return True
        alias_norm = normalize_match(alias)
        value_norm = normalize_match(cleaned)
        if alias_norm in {"должность"}:
            return value_norm in {"должность", "в должности"}
        if alias_norm in {"работает", "работает в организации", "место работы", "работа"}:
            return value_norm in {"работает", "место работы", "работа", "организация"}
        return looks_like_label(cleaned)

    def _all_inline_aliases(self) -> List[str]:
        aliases: List[str] = []
        for values in self.FIELD_ALIASES.values():
            aliases.extend(values)
        return aliases

    def _cut_at_next_inline_marker(self, value: str, current_aliases: Sequence[str]) -> str:
        """Обрезать значение, если в той же строке начинается следующее поле.

        Старый парсер корректно работал с вариантом "Ф.И.О." в отдельной строке,
        но при строке вида "Ф.И.О.: Иванова..., Возраст: 45 лет, Место жительства: ..."
        забирал весь хвост строки в ФИО. Эта функция находит следующую метку поля
        внутри той же строки и возвращает только значение текущего поля.
        """
        current_norm = {normalize_match(alias) for alias in current_aliases}
        best = len(value)
        for alias in self._all_inline_aliases():
            if normalize_match(alias) in current_norm:
                continue
            pattern = self._inline_label_pattern(alias)
            m = re.search(pattern, value, flags=re.IGNORECASE)
            if not m:
                continue
            alias_norm = normalize_match(alias)
            # В значении поля «Должность» слова «врач» / «врач-психиатр»
            # являются реальной должностью, а не началом следующего поля «Врач».
            if "должность" in current_norm and alias_norm in {"врач психиатр", "врач-психиатр"}:
                continue
            if m.start() < best:
                best = m.start()
        # Частый формат без двоеточия: "Иванова И.И., 45 лет, г. Нижний Новгород".
        # Для ФИО возраст в той же строке тоже является границей.
        age = re.search(r"[,;]\s*\d{1,3}\s*(?:лет|года|год)\b", value, flags=re.IGNORECASE)
        if age and age.start() < best:
            best = age.start()
        return value[:best]

    @staticmethod
    def _inline_value_pattern(alias: str) -> str:
        alias_pattern = re.escape(alias).replace(r"\ ", r"\s+")
        # Метка поля должна быть самостоятельным словом/фразой.
        # Так "Работа" не цепляется внутри "Работает", а "ФИО: ..." и "ФИО ..." читаются.
        return rf"(?<![А-Яа-яA-Za-z0-9]){alias_pattern}(?![А-Яа-яA-Za-z0-9])\s*(?:[:№N#.-]\s*)?"

    @staticmethod
    def _inline_label_pattern(alias: str) -> str:
        alias_pattern = re.escape(alias).replace(r"\ ", r"\s+")
        # Метка в середине строки обычно отделена запятой/точкой с запятой/пробелом
        # и имеет после себя ':' или похожий разделитель. Так мы не режем обычный адрес.
        return rf"(?<![А-Яа-яA-Za-z0-9]){alias_pattern}(?![А-Яа-яA-Za-z0-9])\s*(?:[:№N#.-]|$)"
