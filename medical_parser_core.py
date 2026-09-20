from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

from medical_docx_reader import (
    extract_admission_date_from_title_docx,
    extract_docx_text,
    materialize_word_source_as_docx,
    _first_valid_full_date,
    _is_birth_or_demographic_context,
    _is_primary_title_context,
)
from medical_models import PatientData, strip_admission_occurrence_prefix
from medical_parser_sanitize import sanitize_diagnosis
from medical_treatment_detection import has_treatment_section_marker
from medical_text_utils import (
    DIAGNOSIS_STOP_MARKERS,
    clean_value,
    looks_like_label,
    normalize_match,
    normalize_text,
)


class MedicalParserCoreMixin:
    @staticmethod
    def _detect_document_kind(text: str, filename: str = "") -> str:
        """Определить тип любого медицинского документа-источника пациента.

        Тип источника нужен только для корректного извлечения фактов и UX.
        Все распознанные документы сводятся в один PatientData и могут быть
        источником для любого выбранного выходного документа.
        """
        low = normalize_match(text)
        name = normalize_match(filename)
        combined = f"{name} {low}".strip()

        # Сначала самые специфичные документы. Они могут содержать слова
        # «первичный», «госпитализация» и т.п. внутри клинического текста.
        if "выписной эпикриз" in combined:
            return "выписной эпикриз"
        if "совместный осмотр" in combined or "комиссионный осмотр" in combined:
            return "совместный осмотр"
        if "акт для рвк" in combined or ("о состоянии здоровья гражданина" in combined and "военного комиссариата" in combined):
            return "акт для РВК"
        if "вк больничный" in combined or "вк по больнич" in combined:
            return "ВК больничный"
        if "вк на мсэ" in combined or "на мсэ" in combined or "медико-социальн" in combined:
            return "ВК на МСЭ"
        if "осмотр врача приемного покоя" in combined:
            return "осмотр врача приёмного покоя"
        if (
            "направление на госпитализацию" in combined
            or "госпитализируется по направлению" in combined
            or "целесообразна госпитализация" in combined
        ):
            return "направление на госпитализацию"
        if "первичный осмотр" in combined:
            return "первичный осмотр"
        if "в 3 отделение кдп поступает" in low and "анамнез жизни" in low and "психический статус" in low:
            return "медицинский документ пациента"
        return "медицинский документ пациента"

    def parse_docx(self, path: str | Path) -> PatientData:
        # Native DOCX/DOCM are read directly. Legacy binary DOC is materialized
        # once into a temporary DOCX, then *all* parser stages consume that same
        # readable file. This keeps FIO/date/diagnosis/document-kind in one
        # canonical path and avoids opening Microsoft Word twice for one input.
        with materialize_word_source_as_docx(path) as readable_path:
            text = extract_docx_text(readable_path)
            data = self.parse_text(text)
            data.input_document_kind = self._detect_document_kind(text, Path(path).stem)
            episode_admission, episode_discharge = self._extract_episode_dates(text, data.input_document_kind)
            # Для первичного осмотра/направления/приёмного покоя дата рядом с
            # заголовком остаётся самым строгим источником даты поступления.
            # Для выписного эпикриза дата в заголовке — дата выписки, поэтому
            # поступление извлекается из периода лечения.
            title_date = extract_admission_date_from_title_docx(readable_path)
        if episode_admission:
            data.admission_date = episode_admission
        elif title_date:
            data.admission_date = title_date
        if episode_discharge:
            data.discharge_date = episode_discharge
        self._refresh_warnings(data)
        return data

    def parse_text(self, text: str) -> PatientData:
        text = normalize_text(text)
        data = PatientData()
        data.input_document_kind = self._detect_document_kind(text)
        # Full-document scan: if the primary DOCX has no explicit treatment
        # row, the UI must ask the doctor for «Лечение» when any medical
        # document is selected in block 03.
        data.has_treatment_section = has_treatment_section_marker(text)

        inline_lines = self._prepare_inline_lines(text)
        for field_name, aliases in self.FIELD_ALIASES.items():
            value = self._extract_inline(text, aliases, prepared_lines=inline_lines)
            if value:
                # "Проживает - в семье" в анамнезе жизни не является адресом регистрации.
                # Адрес берём только из явных адресных строк или компактной строки пациента.
                if field_name == "registered" and not self._looks_like_address_tail(value):
                    continue
                setattr(data, field_name, value)

        data.admission = strip_admission_occurrence_prefix(data.admission)

        for field_name, aliases in self.BLOCK_ALIASES.items():
            value = self._extract_block(text, aliases)
            if value:
                setattr(data, field_name, value)

        data.admission_date = self._extract_admission_date(text)
        episode_admission, episode_discharge = self._extract_episode_dates(text, data.input_document_kind)
        if episode_admission:
            data.admission_date = episode_admission
        if episode_discharge:
            data.discharge_date = episode_discharge

        # Поддержка компактных медицинских документов: ФИО, возраст и адрес
        # могут быть написаны в одну строку, а не в отдельный столбец.
        self._repair_compact_demographics(data, text)

        # Работа и должность должны подтягиваться из первичного документа в
        # popup-окна как два отдельных значения. Поддерживаем как отдельные
        # поля «Работает в организации» / «Должность», так и одну фразу
        # «Работает в ..., в должности ...».
        self._repair_work_details(data, text)

        # Анамнез жизни может быть не только таблицей/столбцом с явной меткой
        # «Анамнез жизни», но и свободным абзацем: "наследственность - ...
        # Родился... Беременность и роды...". Берём исходные слова и стиль
        # из первичного документа, не пересобирая текст искусственно.
        self._repair_life_anamnesis_from_free_style(data, text)

        if not data.diagnosis:
            diagnosis = self._extract_after_phrase(text, r"был\s+выставлен\s+диагноз\s*[:.]?")
            if diagnosis:
                data.diagnosis = diagnosis

        if data.diagnosis:
            data.diagnosis = sanitize_diagnosis(data.diagnosis)

        for key, value in list(asdict(data).items()):
            if isinstance(value, str) and self._parsed_field_value_is_only_label(key, value):
                setattr(data, key, "")

        if data.diagnosis:
            data.diagnosis = sanitize_diagnosis(data.diagnosis)

        # Фразу направления о целесообразности госпитализации оставляем в данных:
        # врач использует её как часть исходного клинического текста.
        #
        # ВАЖНО: отсутствующие сведения о пациенте не заполняем предположениями.
        # Адрес и эпидемиологический анамнез являются медицинскими фактами и
        # должны происходить только из исходного документа или явного ввода врача.
        # Имена врача/заведующей остаются конфигурационными defaults PatientData,
        # но клинические сведения пациента никогда не синтезируются парсером.

        self._refresh_warnings(data)

        return data

    @staticmethod
    def _refresh_warnings(data: PatientData) -> None:
        """Rebuild parser warnings after late repairs/overrides.

        parse_docx can fill admission_date after parse_text has already run.
        Recomputing warnings prevents stale "missing admission date" messages in
        the UI preview and strict-mode diagnostics.
        """
        data.warnings.clear()
        for field_name in data.missing_critical_fields():
            data.warnings.append(f"Не найдено критическое поле: {field_name}")
        for field_name in data.missing_recommended_fields():
            data.warnings.append(f"Не найдено рекомендуемое поле: {field_name}")
