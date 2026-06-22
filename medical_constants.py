"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from typing import Dict

APP_TITLE = "Медицинские документы — автозаполнение"
DATE_FMT = "%d.%m.%Y"

TEMPLATE_FILES: Dict[str, str] = {
    "primary": "2 Первичный.docx",
    "discharge": "3 Выписной.docx",
    "commission": "4 Комиссионный.docx",
    "vk_mse": "5 ВК на МСЭ.docx",
    "admission_doctor_referral": "7 Направление врача приёмного покоя.docx",
    "sick_leave_vk": "6 ВК больничный.docx",
    "rvk": "6 Акт для рвк.docx",
}

OUTPUT_SUFFIXES: Dict[str, str] = {
    "primary": "Первичный осмотр",
    "discharge": "Выписной эпикриз",
    "commission": "Совместный осмотр",
    "vk_mse": "ВК на МСЭ",
    "admission_doctor_referral": "Осмотр врача приёмного покоя",
    "sick_leave_vk": "ВК больничный",
    "rvk": "Акт для РВК",
}

DOCUMENT_LABELS: Dict[str, str] = {
    "primary": "Первичный осмотр",
    "discharge": "Выписной эпикриз",
    "commission": "Совместный осмотр",
    "vk_mse": "ВК на МСЭ",
    "admission_doctor_referral": "Осмотр врача приёмного покоя",
    "sick_leave_vk": "ВК больничный",
    "rvk": "Акт для РВК",
}

DOCUMENT_ORDER = ("primary", "discharge", "commission", "vk_mse", "admission_doctor_referral", "sick_leave_vk", "rvk")
TARGET_MEDICAL_FACILITY = "ГБУЗ НО «НКЦПЗ» диспансер №2"
