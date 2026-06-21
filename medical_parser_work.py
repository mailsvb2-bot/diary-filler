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


class MedicalParserWorkMixin:
    @staticmethod
    def _is_non_working_org_value(value: str) -> bool:
        normalized = normalize_match(value).strip(" .,:;-")
        return normalized in {
            "не работает",
            "нет",
            "не указан",
            "не указано",
            "безработный",
            "безработная",
            "без работы",
        }

    @classmethod
    def _clean_work_org_value(cls, value: str) -> str:
        value = clean_value(value)
        if not value:
            return ""
        value = re.sub(r"^(?:в\s+организации|организации|в)\s+", "", value, flags=re.IGNORECASE).strip()
        value = value.strip(" ,.;:")
        value = clean_value(value)
        if cls._is_non_working_org_value(value):
            return ""
        return value

    @staticmethod
    def _clean_position_value(value: str) -> str:
        value = clean_value(value)
        if not value:
            return ""
        value = re.sub(r"^(?:должность|в\s+должности)\s*[:.\-]?\s*", "", value, flags=re.IGNORECASE).strip()
        value = value.strip(" ,.;:")
        return clean_value(value)

    @classmethod
    def _split_work_position_value(cls, value: str) -> Tuple[str, str]:
        """Разделить одну рабочую фразу на организацию и должность.

        Примеры:
        - "в ООО «Привет», в должности начальник";
        - "Рассвет, должность: Уборщик";
        - "ООО Ромашка".
        """
        raw = clean_value(value)
        if not raw:
            return "", ""
        m = re.search(
            r"(?:[,;.]?\s*)(?:в\s+должности|должность)\s*[:.\-]?\s*(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
        if not m:
            return cls._clean_work_org_value(raw), ""
        org = cls._clean_work_org_value(raw[:m.start()])
        position = cls._clean_position_value(m.group(1))
        return org, position

    def _repair_work_details(self, data: PatientData, text: str) -> None:
        """Нормализовать место работы и должность из первичного документа.

        Раньше строка "Работает в Рассвет, в должности Уборщик" могла целиком
        попадать в `work_org`. Для popup-окон нужны два отдельных значения.
        """
        if data.work_org:
            org, position_from_org = self._split_work_position_value(data.work_org)
            # Assign even an empty normalized organization: values like
            # ``не работает`` / ``безработный`` are explicit non-working statuses,
            # not organization names, and must be cleared instead of preserved.
            data.work_org = org
            if position_from_org and not data.position:
                data.position = position_from_org

        if data.position:
            data.position = self._clean_position_value(data.position)

        if data.work_org and data.position:
            return

        # Запасной поиск по свободной строке, если общий inline-парсер не смог
        # разделить работу и должность.
        for line in text.splitlines():
            line = normalize_text(line)
            if not line:
                continue
            m = re.search(
                r"работает(?:\s+в\s+организации)?\s*[:.\-]?\s*(.+?)(?:[,;]\s*|\s+)"
                r"(?:в\s+должности|должность)\s*[:.\-]?\s*([^\n.;]+)",
                line,
                flags=re.IGNORECASE,
            )
            if not m:
                continue
            if not data.work_org:
                data.work_org = self._clean_work_org_value(m.group(1))
            if not data.position:
                data.position = self._clean_position_value(m.group(2))
            if data.work_org and data.position:
                break

    def _repair_life_anamnesis_from_free_style(self, data: PatientData, text: str) -> None:
        """Достать анамнез жизни из свободного/анкетного стиля.

        Поддерживает оба рабочих вида первичного осмотра:
        1) строки-анкеты: «наследственность - ...», «Рождение в городе - ...»;
        2) единый абзац: «наследственность - ... Родился в ...».

        Если явный блок «Анамнез жизни» уже найден, не пересобираем его —
        сохраняем стиль и формулировки из документа.
        """
        if data.life_anamnesis and not looks_like_label(data.life_anamnesis):
            return
        m = self.LIFE_ANAMNESIS_START_RE.search(text)
        if not m:
            return
        start = m.start()
        end = self._find_next_marker_pos(text, start + 1, ())
        if end <= start or end == len(text):
            # Страховочная граница для коротких свободных абзацев без следующей
            # явной метки. Не даём случайно забрать весь документ.
            hard = re.search(
                r"(?i)(?:\n|\s)(анамнез\s+заболевания|жалобы|психический\s+статус|"
                r"соматическ\w*\s+статус|сомато-неврологическ\w*\s+статус|"
                r"план\s+обследования|план\s+лечения|лечение\s*[:.-]|диагноз\s*[:.-]|"
                r"эпидемиологический\s+анамнез|врач\s+психиатр|зав\.?)",
                text[start + 1:],
            )
            if hard:
                end = start + 1 + hard.start()
            else:
                end = min(len(text), start + 2200)
        value = self._remove_template_noise(clean_value(text[start:end]))
        if value and not looks_like_label(value):
            data.life_anamnesis = value
