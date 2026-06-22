from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

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


class MedicalParserBlocksMixin:
    def _extract_block(self, text: str, aliases: Sequence[str]) -> str:
        for alias in aliases:
            start = self._find_alias_span(text, alias)
            if not start:
                continue
            value_start = start[1]
            remainder = text[value_start:]
            remainder = re.sub(r"^\s*[:.-]*\s*", "", remainder)
            consumed = len(text[value_start:]) - len(remainder)
            value_start += consumed
            value_end = self._find_next_marker_pos(text, value_start, aliases)
            raw = clean_value(text[value_start:value_end])
            raw = self._remove_template_noise(raw)
            if raw and not looks_like_label(raw):
                return raw
        return ""

    def _extract_after_phrase(self, text: str, phrase_pattern: str) -> str:
        m = re.search(phrase_pattern, text, flags=re.IGNORECASE)
        if not m:
            return ""
        value_start = m.end()
        value_end = self._find_next_marker_pos(text, value_start, ())
        return clean_value(text[value_start:value_end])

    def _extract_admission_date(self, text: str) -> str:
        """Извлечь дату поступления только из строки заголовка.

        Текстовый fallback используется, когда у нас нет DOCX-структуры.
        Он намеренно строгий: дата рождения рядом с ФИО не подходит даже
        как запасной вариант.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""

        # 1) Дата и название документа в одной строке.
        for line in lines[:60]:
            if _is_birth_or_demographic_context(line):
                continue
            if _is_primary_title_context(line):
                value = _first_valid_full_date(line)
                if value:
                    return value

        # 2) Соседние строки: дата отдельно, заголовок отдельно. Только если
        # строка с датой выглядит как чистая дата и рядом нет демографии.
        date_only_re = re.compile(r"^\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?:\s+\d{1,2}:\d{2})?\s*$")
        for idx, line in enumerate(lines[:60]):
            if not date_only_re.match(line):
                continue
            neighbors = lines[max(0, idx - 1): min(len(lines), idx + 2)]
            if any(_is_birth_or_demographic_context(item) for item in neighbors):
                continue
            if any(_is_primary_title_context(item) for item in neighbors):
                value = _first_valid_full_date(line)
                if value:
                    return value

        return ""

    def _find_alias_span(self, text: str, alias: str) -> Optional[Tuple[int, int]]:
        """Найти метку раздела, а не случайное слово внутри текста.

        Особенно важно для слова «Лечение»: оно не должно срабатывать внутри
        фразы «За время лечения...», но должно срабатывать на «Лечение: ...»
        и на отдельный заголовок «Лечение».
        """
        pattern = self._alias_pattern(alias)
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if self._is_valid_section_marker_occurrence(text, m.start(), m.end(), alias):
                return (m.start(), m.end())
        return None

    def _find_next_marker_pos(self, text: str, start_pos: int, current_aliases: Sequence[str]) -> int:
        best = len(text)
        current_norm = {normalize_match(a) for a in current_aliases}
        for marker in self.SECTION_MARKERS:
            if normalize_match(marker) in current_norm:
                continue
            pattern = self._alias_pattern(marker)
            for m in re.finditer(pattern, text[start_pos:], flags=re.IGNORECASE):
                pos = start_pos + m.start()
                end = start_pos + m.end()
                if not self._is_valid_section_marker_occurrence(text, pos, end, marker):
                    continue
                if pos < best:
                    best = pos
                    break
        return best

    @staticmethod
    def _is_valid_section_marker_occurrence(text: str, start: int, end: int, marker: str) -> bool:
        before = text[max(0, start - 3):start]
        after = text[end:end + 8]
        at_line_start = start == 0 or "\n" in before or not text[:start].strip()
        has_label_separator = bool(re.match(r"\s*(?:[:№N#.-]|$)", after))
        marker_norm = normalize_match(marker)
        # «На основании данных ... установлен диагноз» часто идёт как полноценное
        # предложение без двоеточия, поэтому разрешаем его как границу.
        if marker_norm.startswith("на основании"):
            return True
        if at_line_start:
            return True
        # В одну строку разделы тоже могут идти как метки: "Лечение: ... Диагноз: ...".
        # Требуем разделитель после метки, чтобы не резать обычные слова внутри фраз.
        return has_label_separator

    @staticmethod
    def _alias_pattern(alias: str) -> str:
        alias = re.escape(alias)
        alias = alias.replace(r"\ ", r"\s+")
        alias = alias.replace("ё", "[её]").replace("Ё", "[ЕЁ]")
        return alias

    @staticmethod
    def _remove_template_noise(text: str) -> str:
        noisy_patterns = [
            r"сюда\s+подставлять[^\n]*",
            r"сюда\s+подставляется[^\n]*",
            r"выбирается\s+в\s+ui",
        ]
        for pat in noisy_patterns:
            text = re.sub(pat, "", text, flags=re.IGNORECASE)
        return normalize_text(text)
