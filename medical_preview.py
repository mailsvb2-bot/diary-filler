"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

from medical_expert import build_expert_anamnesis
from medical_models import PatientData
from medical_parser import sanitize_diagnosis
from medical_text_utils import normalize_text

def format_preview(data: PatientData) -> str:
    lines = [
        "📋 Извлечённые данные",
        f"Тип первичного документа: {data.input_document_kind or '—'}",
        f"Ф.И.О.: {data.fio or '—'}",
        f"История болезни №: {data.case_number or '—'}",
        f"Год/дата рождения: {data.birth or '—'}",
        f"Адрес: {data.registered or '—'}",
        f"Дата госпитализации: {data.admission_date or '—'}",
        f"Дата выписки: {data.discharge_date or '—'}",
        f"Поступает: {data.admission or '—'}",
        f"Диагноз: {sanitize_diagnosis(data.diagnosis) or '—'}",
        f"План лечения: {shorten(data.treatment_plan, 140) or '—'}",
        f"Экспертный анамнез: {shorten(build_expert_anamnesis(data), 140) or '—'}",
        f"ЭПИ: {len(data.epi_text)} символов",
        f"Акт РВК №: {data.rvk_act_number or '—'}",
        f"Военкомат РВК: {data.rvk_military_commissariat or '—'}",
        f"Работа/должность РВК: {data.rvk_work_position or '—'}",
        f"ВК на МСЭ: дата {data.vk_date or '—'}, протокол № {data.vk_protocol_number or '—'}, от {data.vk_protocol_date or '—'}",
        f"ВК больничный: дата {data.sick_leave_vk_date or '—'}, протокол № {data.sick_leave_vk_protocol_number or '—'}, от {data.sick_leave_vk_protocol_date or '—'}, комиссия {data.sick_leave_vk_commission_date or '—'}",
        f"Жалобы: {shorten(data.complaints, 180) or '—'}",
        f"Анамнез жизни: {len(data.life_anamnesis)} символов",
        f"Анамнез заболевания: {len(data.disease_anamnesis)} символов",
        f"Психический статус: {len(data.mental_status)} символов",
    ]
    if data.warnings:
        lines.append("")
        lines.append("⚠️ Предупреждения:")
        lines.extend(f"• {w}" for w in data.warnings)
    return "\n".join(lines)


def shorten(text: str, limit: int) -> str:
    text = normalize_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
