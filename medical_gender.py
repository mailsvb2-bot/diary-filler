"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import copy
import re

from docx.document import Document as DocxDocument

try:
    from diary_filler import adapt_text_to_patient_gender, detect_gender_from_patient_name
except Exception:  # pragma: no cover - защитный fallback для автономного использования модуля
    def detect_gender_from_patient_name(_patient_name: str) -> str | None:
        return None

    def adapt_text_to_patient_gender(text: str, _gender: str | None) -> tuple[str, int]:
        return text, 0

from medical_constants import TARGET_MEDICAL_FACILITY
from medical_docx_editor import iter_all_paragraphs, remove_epi_mentions_from_document, set_paragraph_text
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
    """
    gender = patient_gender(data)
    if gender not in {"male", "female"}:
        return

    for paragraph in list(iter_all_paragraphs(doc)):
        original = paragraph.text or ""
        if not original.strip():
            continue
        # Защита от порчи фраз вида «установлен диагноз: ...» и названий МКБ.
        # Клинические описания вокруг этих строк уже адаптированы на уровне данных.
        if "диагноз" in normalize_match(original):
            continue
        updated, changed = adapt_text_to_patient_gender(original, gender)
        if changed and updated != original:
            set_paragraph_text(paragraph, updated)



def normalize_facility_references_in_document(doc: DocxDocument) -> None:
    """Единообразно заменить старые названия учреждения/отделения в итоговых DOCX.

    Пользовательский контракт: если в шаблоне или тексте встречается
    «ГБУЗ НО ПБ №2» либо «отделение №3», в результате должно быть
    «ГБУЗ НО «НКЦПЗ» диспансер №2». Отдельно нормализуем финальную фразу
    направления/осмотра приёмного покоя.
    """
    target = TARGET_MEDICAL_FACILITY
    for paragraph in list(iter_all_paragraphs(doc)):
        original = paragraph.text or ""
        if not original.strip():
            continue
        normalized = normalize_match(original)
        if normalized.startswith("направляется на лечение") or normalized.startswith("направляется в гбуз"):
            set_paragraph_text(paragraph, f"Направляется в {target}")
            continue
        updated = original
        replacements = [
            (r"ГБУЗ\s*НО\s*ПБ\s*№\s*2", target),
            (r"ГБУЗНО\s*«?Психиатрическая\s+больница\s*№\s*2»?(?:\s*г\.\s*Н\.\s*Новгорода)?", target),
            (r"ГБУЗ\s*НО\s*«?Психиатрическая\s+больница\s*№\s*2»?(?:\s*г\.\s*Н\.\s*Новгорода)?", target),
            (r"отделени[ея]\s*№\s*3", target),
        ]
        for pattern, replacement in replacements:
            updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
        updated = re.sub(rf"в\s+{re.escape(target)}", f"в {target}", updated, flags=re.IGNORECASE)
        updated = re.sub(r"\s+", " ", updated).strip()
        if updated != original:
            set_paragraph_text(paragraph, updated)


def finalize_medical_document(doc: DocxDocument, data: PatientData) -> None:
    """Общие финальные правки перед сохранением любого медицинского документа."""
    normalize_facility_references_in_document(doc)
    adapt_document_to_patient_gender(doc, data)
    if not data.epi_text:
        remove_epi_mentions_from_document(doc)
