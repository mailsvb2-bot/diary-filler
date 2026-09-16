"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import copy
import re

from docx.document import Document as DocxDocument

from shared_gender import GENDER_WORD_PAIRS, adapt_text_to_patient_gender, detect_gender_from_patient_name
from medical_constants import TARGET_MEDICAL_FACILITY
from medical_formatting import format_staff_instrumental_short_name, format_staff_short_name
from medical_docx_editor import (
    apply_readable_section_spacing,
    iter_all_paragraphs,
    remove_epi_mentions_from_document,
    replace_paragraph_regex_preserving_runs,
    set_paragraph_text,
)
from medical_models import PatientData
from medical_text_utils import normalize_match

GENDER_ADAPTED_PATIENT_FIELDS = (
    "complaints",
    "life_anamnesis",
    "disease_anamnesis",
    "mental_status",
    "somatic_status",
    "treatment_plan",
    "epidemiology",
    "admission",
    "psych_account",
    "epi_text",
)

_FACILITY_REFERENCE_PATTERNS = (
    re.compile(r"ГБУЗ\s*НО\s*ПБ\s*№\s*2", re.IGNORECASE),
    re.compile(
        r"ГБУЗНО\s*«?Психиатрическая\s+больница\s*№\s*2»?(?:\s*г\.\s*Н\.\s*Новгорода)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"ГБУЗ\s*НО\s*«?Психиатрическая\s+больница\s*№\s*2»?(?:\s*г\.\s*Н\.\s*Новгорода)?",
        re.IGNORECASE,
    ),
    re.compile(r"отделени[ея]\s*№\s*3", re.IGNORECASE),
)
_FACILITY_REFERENCE_PREFILTERS = ("гбуз", "отделени")


def _preserve_case_for_document(source: str, target: str) -> str:
    if source.isupper():
        return target.upper()
    if source[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


def patient_gender(data: PatientData) -> str | None:
    """Определить род пациента по первой части ФИО, как в заполнителе дневников."""
    return detect_gender_from_patient_name(data.fio or data.output_fio or "")


def adapt_patient_data_to_gender(data: PatientData) -> PatientData:
    """Вернуть копию данных, где клинические текстовые блоки согласованы с родом пациента.

    Диагноз, ФИО, адрес, даты, подписи и служебные реквизиты не трогаем: они
    не являются текстом о пациенте и не должны портиться морфологическим проходом.
    """
    gender = patient_gender(data)
    if gender not in {"male", "female"}:
        return data

    adapted = copy.deepcopy(data)
    for field_name in GENDER_ADAPTED_PATIENT_FIELDS:
        value = getattr(adapted, field_name, "")
        if not isinstance(value, str) or not value:
            continue
        new_value, _changed = adapt_text_to_patient_gender(value, gender)
        setattr(adapted, field_name, new_value)
    return adapted


def adapt_document_to_patient_gender(doc: DocxDocument, data: PatientData) -> None:
    """Применить ту же муж/жен коррекцию к итоговому DOCX.

    Это нужно для шаблонных фраз самих документов: например,
    «Находился на лечении...» -> «Находилась на лечении...» для женской фамилии.
    Диагнозные строки оставляем как есть: диагноз — отдельная медицинская сущность,
    а не грамматическое описание пациента.

    Performance note: the replacement contract remains strictly sequential, but
    regex work is skipped when the current paragraph cannot contain the source
    token. This preserves the old cascading semantics while avoiding tens of
    thousands of no-op run-preserving scans per generated комплект.
    """
    gender = patient_gender(data)
    if gender not in {"male", "female"}:
        return

    pairs = sorted(GENDER_WORD_PAIRS, key=lambda pair: max(len(pair[0]), len(pair[1])), reverse=True)
    prepared_pairs: list[tuple[str, re.Pattern[str], str]] = []
    for male, female in pairs:
        source, target = (female, male) if gender == "male" else (male, female)
        pattern = re.compile(
            rf"(?<![A-Za-zА-Яа-яЁё]){re.escape(source)}(?![A-Za-zА-Яа-яЁё])",
            re.IGNORECASE,
        )
        prepared_pairs.append((source.casefold(), pattern, target))

    for paragraph in list(iter_all_paragraphs(doc)):
        original = paragraph.text or ""
        if not original.strip():
            continue
        # Защита от порчи фраз вида «установлен диагноз: ...» и названий МКБ.
        # Клинические описания вокруг этих строк уже адаптированы на уровне данных.
        if "диагноз" in normalize_match(original):
            continue
        # Apply the same pair rules directly to runs so a local gender change
        # does not flatten bold/italic/underlined fragments elsewhere in the paragraph.
        # The cheap casefold containment check is only a negative filter: every
        # possible match still goes through the exact historical regex/replacer.
        current_folded = original.casefold()
        for source_folded, pattern, target in prepared_pairs:
            if source_folded not in current_folded:
                continue
            changed = replace_paragraph_regex_preserving_runs(
                paragraph,
                pattern,
                lambda match, target=target: _preserve_case_for_document(match.group(0), target),
            )
            if changed:
                # A replacement can theoretically introduce the source token of a
                # later rule, so refresh the prefilter text and preserve the exact
                # sequential/cascading behavior of the previous implementation.
                current_folded = (paragraph.text or "").casefold()



def normalize_facility_references_in_document(doc: DocxDocument) -> None:
    """Единообразно заменить старые названия учреждения/отделения в итоговых DOCX.

    Пользовательский контракт: если в шаблоне или тексте встречается
    «ГБУЗ НО ПБ №2» либо «отделение №3», в результате должно быть
    «ГБУЗ НО «НКЦПЗ» диспансер №2». Отдельно нормализуем финальную фразу
    направления/осмотра приёмного покоя.

    Performance note: cheap casefold containment checks are negative-only
    prefilters. Every paragraph that can match an established facility regex
    still goes through the exact historical run-preserving replacement path.
    """
    target = TARGET_MEDICAL_FACILITY
    for paragraph in list(iter_all_paragraphs(doc)):
        original = paragraph.text or ""
        if not original.strip():
            continue

        folded = original.casefold()
        if "направляется" in folded:
            normalized = normalize_match(original)
            if normalized.startswith("направляется на лечение") or normalized.startswith("направляется в гбуз"):
                set_paragraph_text(paragraph, f"Направляется в {target}")
                continue

        if not any(token in folded for token in _FACILITY_REFERENCE_PREFILTERS):
            continue
        for pattern in _FACILITY_REFERENCE_PATTERNS:
            replace_paragraph_regex_preserving_runs(paragraph, pattern, target)


def normalize_staff_references_in_document(doc: DocxDocument, data: PatientData) -> None:
    """Replace historical template staff names only in explicit staff-role fields.

    Never scan arbitrary patient/clinical text for surnames: a patient can legally
    have the same surname/initials as one of the historical template employees.
    """
    configured = {
        "doctor": format_staff_short_name(data.doctor),
        "head": format_staff_short_name(data.head),
        "head_instrumental": format_staff_instrumental_short_name(data.head),
        "deputy": format_staff_short_name(data.deputy_chief),
        "deputy_instrumental": format_staff_instrumental_short_name(data.deputy_chief),
    }
    doctor_role = r"(?:Лечащий\s+врач|Врач[\s-]*психиатр)"
    head_role = r"(?:Зав(?:едующ(?:ий|ая)|\.)?\s*(?:отделени(?:ем|я)|отд\.?))"
    deputy_role = r"(?:Зам(?:еститель|\.)?\s*(?:глав(?:ного)?|гл)\.?\s+врача|Председатель\s+ВК)"

    replacements: list[tuple[str, str, str]] = []
    if configured["doctor"] and configured["doctor"] != "Балаганин С.В":
        replacements.append((doctor_role, r"Балаганин\s+С\.В\.?", configured["doctor"]))
    if configured["head"] and configured["head"] != "Можарова Е.А.":
        replacements.extend([
            (head_role, r"Можарова\s+Е\.А\.?", configured["head"]),
            (head_role, r"Можаровой\s+Е\.А\.?", configured["head_instrumental"]),
        ])
    if configured["deputy"] and configured["deputy"] != "Зуйкова А.А.":
        replacements.extend([
            (deputy_role, r"Зуйкова\s+А\.А\.?", configured["deputy"]),
            (deputy_role, r"Зуйковой\s+А\.А\.?", configured["deputy_instrumental"]),
        ])
    if not replacements:
        return

    compiled = [
        (
            re.compile(
                rf"(?P<role>{role})(?P<separator>[\t :–—-]+)(?P<legacy>{legacy})",
                re.IGNORECASE,
            ),
            replacement,
        )
        for role, legacy, replacement in replacements
        if replacement
    ]
    for paragraph in list(iter_all_paragraphs(doc)):
        if not (paragraph.text or "").strip():
            continue
        for pattern, replacement in compiled:
            replace_paragraph_regex_preserving_runs(
                paragraph,
                pattern,
                lambda match, replacement=replacement: (
                    f"{match.group('role')}{match.group('separator')}{replacement}"
                ),
            )


def finalize_medical_document(doc: DocxDocument, data: PatientData) -> None:
    """Общие финальные правки перед сохранением любого медицинского документа."""
    normalize_facility_references_in_document(doc)
    normalize_staff_references_in_document(doc, data)
    adapt_document_to_patient_gender(doc, data)
    if not data.epi_text:
        remove_epi_mentions_from_document(doc)
    apply_readable_section_spacing(doc)