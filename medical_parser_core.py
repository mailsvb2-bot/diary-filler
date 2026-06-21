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
    def _detect_document_kind(text: str) -> str:
        """Определить тип входного первичного документа для статуса/диагностики.

        Это не влияет на схему данных: и направление, и первичный осмотр
        разбираются в один PatientData и затем используются всеми выбранными
        документами.
        """
        low = normalize_match(text)
        # Сначала направление: в реальных файлах оно может содержать слова
        # «первичный осмотр» как часть текста/шапки, но popup нужен именно для
        # направления на госпитализацию.
        if (
            "направление на госпитализацию" in low
            or "госпитализируется по направлению" in low
            or "целесообразна госпитализация" in low
        ):
            return "направление на госпитализацию"
        if "первичный осмотр" in low:
            return "первичный осмотр"
        if "в 3 отделение кдп поступает" in low and "анамнез жизни" in low and "психический статус" in low:
            return "первичный документ пациента"
        return "первичный документ"

    def parse_docx(self, path: str | Path) -> PatientData:
        text = extract_docx_text(path)
        data = self.parse_text(text)
        # Дата поступления в DOCX имеет один источник истины: заголовок
        # документа / имя файла рядом с названием. Если структурный DOCX-поиск
        # нашёл дату рядом с заголовком, он имеет приоритет. Если нет, сохраняем
        # строгий text-fallback из parse_text вместо обнуления уже найденной даты.
        title_date = extract_admission_date_from_title_docx(path)
        if title_date:
            data.admission_date = title_date
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

        for field_name, aliases in self.FIELD_ALIASES.items():
            value = self._extract_inline(text, aliases)
            if value:
                # "Проживает - в семье" в анамнезе жизни не является адресом регистрации.
                # Адрес берём только из явных адресных строк или компактной строки пациента.
                if field_name == "registered" and not self._looks_like_address_tail(value):
                    continue
                setattr(data, field_name, value)

        for field_name, aliases in self.BLOCK_ALIASES.items():
            value = self._extract_block(text, aliases)
            if value:
                setattr(data, field_name, value)

        data.admission_date = self._extract_admission_date(text)

        # Поддержка компактных первичных документов: ФИО, возраст и адрес
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

        if not data.registered:
            data.registered = "Нижний Новгород"
        if not data.epidemiology:
            data.epidemiology = (
                "со слов пациента, за пределы Нижегородской области в течение трёх предыдущих месяцев "
                "не выезжал, в контакте с инфекционными больными не был. Венерические заболевания, "
                "туберкулёз, вирусные гепатиты отрицает."
            )
        if not data.doctor:
            data.doctor = "Балаганин С.В"
        if not data.head:
            data.head = "Можарова Е.А."

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
