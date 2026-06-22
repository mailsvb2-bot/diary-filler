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


class MedicalParserDemographicsMixin:
    def _repair_compact_demographics(self, data: PatientData, text: str) -> None:
        """Восстановить ФИО/возраст/адрес из одной строки.

        Поддерживаемые варианты:
        - "Ф.И.О.: Иванова Ирина Ивановна, Возраст: 45 лет, Место жительства: Н. Новгород"
        - "Ф.И.О.: Иванова Ирина Ивановна, 45 лет, Н. Новгород, ул. ..."
        - "Иванова Ирина Ивановна, 45 лет, проживает: Н. Новгород ..."

        Значения из явно найденных отдельных строк не перетираются, кроме случая,
        когда в ФИО явно попал хвост с возрастом/адресом.
        """
        candidates: List[str] = []
        if data.fio:
            candidates.append(data.fio)
        candidates.extend(text.splitlines())

        for candidate in candidates:
            parsed = self._parse_compact_demographics_line(candidate)
            if not parsed:
                continue
            fio, birth_or_age, address, work_org = parsed

            if fio and (not data.fio or self._fio_value_looks_overgrown(data.fio)):
                data.fio = fio
            if birth_or_age and not data.birth:
                data.birth = birth_or_age
            if address and (
                not data.registered
                or data.registered == "Нижний Новгород"
                or not self._looks_like_address_tail(data.registered)
            ):
                data.registered = address
            if work_org and not data.work_org:
                data.work_org = work_org

            if data.fio and data.birth and data.registered and not self._fio_value_looks_overgrown(data.fio):
                break

    @staticmethod
    def _fio_value_looks_overgrown(value: str) -> bool:
        low = normalize_match(value)
        return bool(
            re.search(r"\b\d{1,3}\s*(?:лет|года|год)\b", low)
            or "проживает" in low
            or "место жительства" in low
            or "адрес" in low
            or "зарегистрирован" in low
            or "возраст" in low
            or bool(re.search(r"\b[12]\d{3}\s*г\.?\s*р?\.?", low))
        )

    def _parse_compact_demographics_line(self, line: str) -> Optional[Tuple[str, str, str, str]]:
        raw = normalize_text(line)
        if not raw:
            return None
        low = normalize_match(raw)

        has_demographic_hint = any(
            hint in low
            for hint in (
                "ф.и.о", "фио", "возраст", "лет", "года", "год", "год рождения", "дата рождения",
                "проживает", "место жительства", "адрес", "зарегистрирован", "г.", "город", "улица", "ул.",
                "работает", "место работы", "работа", "ооо", "ао", "пао", "ип", "гбуз", "мбуз"
            )
        )
        if not has_demographic_hint:
            return None

        # Удаляем ведущие служебные подписи, но оставляем значение.
        compact = re.sub(
            r"^(?:ф\.\s*и\.\s*о\.?|фио|фамилия\s+имя\s+отчество|пациент(?:ка)?|больн(?:ой|ая))\s*[:.-]?\s*",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()

        fio = ""
        fio_match = re.search(
            r"\b([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
            r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
            r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\b",
            compact,
        )
        if fio_match:
            fio = clean_value(fio_match.group(1))
        else:
            # Редкий вариант без отчества: берём только если строка явно начинается с ФИО.
            two = re.match(
                r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\b",
                compact,
            )
            if two and ("фио" in low or "ф.и.о" in low):
                fio = clean_value(two.group(1))

        # Возраст / год рождения / дата рождения.
        birth_or_age = ""
        labelled_birth = re.search(
            r"(?:возраст|год\s+рождения|дата\s+рождения|г\.\s*р\.)\s*[:.-]?\s*"
            r"(\d{1,3}\s*(?:лет|года|год)?|\d{2}\.\d{2}\.(?:\d{2}|\d{4})|[12]\d{3}\s*(?:г\.?\s*р\.?)?)",
            compact,
            flags=re.IGNORECASE,
        )
        if labelled_birth:
            birth_or_age = clean_value(labelled_birth.group(1))
        else:
            age = re.search(r"\b(\d{1,3}\s*(?:лет|года|год))\b", compact, flags=re.IGNORECASE)
            if age:
                birth_or_age = clean_value(age.group(1))
            else:
                date_or_year = re.search(r"\b(\d{2}\.\d{2}\.(?:\d{2}|\d{4})|[12]\d{3}\s*(?:г\.?\s*р\.?)?)\b", compact)
                if date_or_year:
                    birth_or_age = clean_value(date_or_year.group(1))

        # Адрес / место жительства и место работы.
        address = ""
        work_org = ""

        labelled_work = re.search(
            r"(?<![А-Яа-яA-Za-z0-9])(?:работает(?:\s+в\s+организации)?|место\s+работы|работа)"
            r"(?![А-Яа-яA-Za-z0-9])\s*[:.-]?\s*(.+)$",
            compact,
            flags=re.IGNORECASE,
        )
        if labelled_work and re.search(r"(?:^|\s)не\s+работает\b", compact[:labelled_work.end()], flags=re.IGNORECASE):
            labelled_work = None
        if labelled_work:
            work_org = clean_value(labelled_work.group(1))
            work_org = self._cut_at_next_inline_marker(work_org, self.FIELD_ALIASES["work_org"])
            work_org = clean_value(work_org)

        labelled_address = re.search(
            r"(?:место\s+жительства|адрес(?:\s+проживания|\s+регистрации|\s+места\s+жительства)?|проживает|зарегистрирован(?:а)?(?:\s+по\s+адресу)?)"
            r"\s*[:.-]?\s*(.+)$",
            compact,
            flags=re.IGNORECASE,
        )
        if labelled_address:
            address = clean_value(labelled_address.group(1))
            address = self._cut_at_next_inline_marker(address, self.FIELD_ALIASES["registered"])
            address, inline_work = self._split_address_work_tail(address)
            if inline_work and not work_org:
                work_org = inline_work
            address = clean_value(address)
        elif birth_or_age:
            # Если адрес без подписи идёт после возраста: "..., 45 лет, Н. Новгород, ул. ..., ООО Завод".
            pos = compact.lower().find(birth_or_age.lower())
            if pos >= 0:
                tail = compact[pos + len(birth_or_age):]
                tail = re.sub(r"^[\s,;:.-]+", "", tail)
                if self._looks_like_address_tail(tail):
                    address, inline_work = self._split_address_work_tail(tail)
                    address = clean_value(address)
                    if inline_work and not work_org:
                        work_org = inline_work

        if not fio and not birth_or_age and not address and not work_org:
            return None
        return fio, birth_or_age, address, work_org

    @staticmethod
    def _split_address_work_tail(text: str) -> Tuple[str, str]:
        """Разделить хвост компактной строки на адрес и место работы.

        Пример: "г. Нижний Новгород, ул. Ленина 34-15, ООО Завод".
        Возвращает адрес без организации и найденную организацию.
        """
        raw = clean_value(text)
        if not raw:
            return "", ""
        org_pattern = (
            r"(?:,|;|\s)\s*("
            r"(?:ООО|ОАО|АО|ПАО|ЗАО|ИП|ГБУЗ|МБУЗ|ФГБУ|ФКУ|ГУФСИН|МВД|МОУ|МАОУ|МБОУ|ГКУ|АНО)"
            r"\b.*)$"
        )
        m = re.search(org_pattern, raw, flags=re.IGNORECASE)
        if not m:
            return raw, ""
        work = clean_value(m.group(1))
        address = clean_value(raw[:m.start(1)]).rstrip(" ,;")
        return address, work

    @staticmethod
    def _looks_like_address_tail(text: str) -> bool:
        low = normalize_match(text)
        if not low or looks_like_label(low):
            return False
        address_hints = (
            "г.", "город", "н.", "нижний", "новгород", "ул", "улица", "просп", "пр-т",
            "пер.", "дом", "д.", "кв", "район", "область", "пос", "село", "деревня"
        )
        return any(hint in low for hint in address_hints)
