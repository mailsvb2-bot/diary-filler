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

    def _extract_episode_dates(self, text: str, document_kind: str = "") -> tuple[str, str]:
        """Извлечь даты текущего эпизода без угадывания по случайным датам.

        Возвращает ``(дата поступления, дата выписки)``. Для выписного
        эпикриза/Акта РВК обе даты надёжно задаются периодом ``с ... по ...``.
        Для ВК по больничному конец периода — дата комиссии, поэтому как дату
        выписки его не используем.
        """
        value = normalize_text(text or "")
        if not value:
            return "", ""
        kind = normalize_match(document_kind)
        date_token = r"(?:\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}|\d{6,8})"

        def norm(raw: str) -> str:
            return _first_valid_full_date(raw or "")

        # Самый сильный источник: период именно текущего пребывания/обследования.
        period_re = re.compile(
            rf"(?i)(?:находил(?:ся|ась)?|находится)\s+[^\n]{{0,220}}?\bс\s+({date_token})\s+\bпо\s+({date_token})"
        )
        match = period_re.search(value)
        if match:
            admission = norm(match.group(1))
            end_date = norm(match.group(2))
            if admission:
                if "выписной эпикриз" in kind or "акт для рвк" in kind:
                    return admission, end_date
                return admission, ""

        admission = ""
        discharge = ""

        # ВК по больничному и некоторые сторонние формы указывают только
        # начало текущего лечения: «Находится на лечении с 10.06.2026».
        # Это надёжная дата поступления, но не источник даты выписки.
        current_treatment = re.search(
            rf"(?i)(?:находил(?:ся|ась)?|находится)\s+[^\n]{{0,180}}?\bс\s+({date_token})",
            value,
        )
        if current_treatment:
            admission = norm(current_treatment.group(1))
            if admission:
                return admission, ""

        # Явные подписи безопаснее любых дат внутри анамнеза.
        for pattern in (
            rf"(?i)дата\s+(?:поступления|госпитализации)\s*[:.-]?\s*({date_token})",
            rf"(?i)поступил(?:а)?\s+в\s+стационар\s*[:.-]?\s*({date_token})",
        ):
            match = re.search(pattern, value)
            if match:
                admission = norm(match.group(1))
                if admission:
                    break
        for pattern in (
            rf"(?i)дата\s+выписки\s*[:.-]?\s*({date_token})",
            rf"(?i)выписан(?:а)?\s+из\s+стационара\s*[:.-]?\s*({date_token})",
        ):
            match = re.search(pattern, value)
            if match:
                discharge = norm(match.group(1))
                if discharge:
                    break

        # В заголовке выписного эпикриза первая дата — это дата выписки.
        if "выписной эпикриз" in kind and not discharge:
            for line in value.splitlines()[:40]:
                if "выписной эпикриз" not in normalize_match(line):
                    continue
                discharge = _first_valid_full_date(line)
                if discharge:
                    break
        return admission, discharge

    def _extract_source_document_metadata(self, data: PatientData, text: str) -> None:
        """Recover explicit document-specific реквизиты from reusable sources.

        These fields are metadata printed by our own renderers (commission/VK/RVK),
        not inferred clinical facts. Extraction is deliberately format-bound:
        absent or ambiguous values stay empty so the UI can ask the doctor.
        """
        value = normalize_text(text or "")
        if not value:
            return
        kind = normalize_match(data.input_document_kind)
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        date_token = r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{6,8})"

        def first_date(raw: str) -> str:
            return _first_valid_full_date(raw or "")

        if "совместный осмотр" in kind:
            for line in lines[:60]:
                if "совместный осмотр" not in normalize_match(line):
                    continue
                if not data.commission_date:
                    data.commission_date = first_date(line)
                if not data.commission_number:
                    match = re.search(r"№\s*([^\n]+?)\s*$", line)
                    if match:
                        data.commission_number = clean_value(match.group(1)).strip(" .,:;")
                break

        if kind in {"вк на мсэ", "вк больничный"}:
            protocol_number = ""
            protocol_date = ""
            committee_date = ""
            for line in lines[:120]:
                normalized = normalize_match(line)
                if not protocol_number and "выписка из протокола" in normalized:
                    match = re.search(r"(?i)выписка\s+из\s+протокола\s*№\s*(.+?)\s*$", line)
                    if match:
                        protocol_number = clean_value(match.group(1)).strip(" .,:;")
                if not protocol_date and re.match(r"(?i)^\s*от\b", line):
                    match = re.search(rf"(?i)^\s*от\s+({date_token})", line)
                    if match:
                        protocol_date = first_date(match.group(1))
                if not committee_date and re.fullmatch(rf"\s*{date_token}\s*", line):
                    committee_date = first_date(line)

            if "вк на мсэ" in kind:
                data.vk_date = data.vk_date or committee_date
                data.vk_protocol_number = data.vk_protocol_number or protocol_number
                data.vk_protocol_date = data.vk_protocol_date or protocol_date
            else:
                data.sick_leave_vk_date = data.sick_leave_vk_date or committee_date
                data.sick_leave_vk_protocol_number = data.sick_leave_vk_protocol_number or protocol_number
                data.sick_leave_vk_protocol_date = data.sick_leave_vk_protocol_date or protocol_date
                for line in lines[:120]:
                    if "дата проведения комиссии" not in normalize_match(line):
                        continue
                    explicit = first_date(line)
                    if explicit:
                        data.sick_leave_vk_commission_date = (
                            data.sick_leave_vk_commission_date or explicit
                        )
                    break

        if "акт для рвк" in kind:
            for line in lines[:100]:
                normalized = normalize_match(line)
                if not data.rvk_act_number and "о состоянии здоровья гражданина" in normalized:
                    match = re.search(
                        r"(?i)о\s+состоянии\s+здоровья\s+гражданина\s*№\s*(.+?)\s*$",
                        line,
                    )
                    if match:
                        data.rvk_act_number = clean_value(match.group(1)).strip(" .,:;")
                if not data.rvk_military_commissariat and "военного комиссариата" in normalized:
                    match = re.search(
                        r"(?i)военного\s+комиссариата\s+(.+?)(?:[.;]|$)",
                        line,
                    )
                    if match:
                        data.rvk_military_commissariat = clean_value(match.group(1)).strip(" .,:;")

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
