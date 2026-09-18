"""Regression lock for DOCX section-boundary integrity.

Generated patient text must never become template structure, and every renderer
alias used to locate a block must also be a valid boundary marker.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document

from medical_docx_editor import DocxBlockEditor
from medical_markers import (
    COMMISSION_MARKERS,
    DISCHARGE_MARKERS,
    PRIMARY_MARKERS,
    RVK_MARKERS,
    SICK_LEAVE_VK_MARKERS,
    VK_MSE_MARKERS,
)
from medical_text_utils import normalize_match


REQUIRED_ALIASES = {
    "PRIMARY_MARKERS": {
        "ФИО",
        "Дата рождения",
        "Жалобы",
        "Диагноз",
        "Врач-психиатр",
        "Зав. отд.",
    },
    "DISCHARGE_MARKERS": {
        "Жалобы",
        "Психический статус",
        "Соматический статус",
    },
    "COMMISSION_MARKERS": {
        "Жалобы",
        "Психический статус",
        "Сомато-неврологический статус",
        "Диагноз",
    },
    "VK_MSE_MARKERS": {
        "Психический статус",
        "Соматический статус",
    },
    "SICK_LEAVE_VK_MARKERS": {
        "Психический статус",
        "Соматический статус",
    },
    "RVK_MARKERS": {
        "ФИО",
        "Соматический статус",
    },
}

MARKER_SETS = {
    "PRIMARY_MARKERS": PRIMARY_MARKERS,
    "DISCHARGE_MARKERS": DISCHARGE_MARKERS,
    "COMMISSION_MARKERS": COMMISSION_MARKERS,
    "VK_MSE_MARKERS": VK_MSE_MARKERS,
    "SICK_LEAVE_VK_MARKERS": SICK_LEAVE_VK_MARKERS,
    "RVK_MARKERS": RVK_MARKERS,
}


def _assert_alias_coverage() -> None:
    for name, required in REQUIRED_ALIASES.items():
        actual = {normalize_match(item) for item in MARKER_SETS[name]}
        missing = sorted(item for item in required if normalize_match(item) not in actual)
        if missing:
            raise AssertionError(f"{name} misses renderer boundary aliases: {missing}")


def _assert_inserted_marker_like_patient_text_never_becomes_structure() -> None:
    doc = Document()
    doc.add_paragraph("Жалобы")
    doc.add_paragraph("старые жалобы шаблона")
    doc.add_paragraph("Анамнез жизни")
    doc.add_paragraph("старый анамнез шаблона")
    doc.add_paragraph("Психический статус")
    doc.add_paragraph("старый психический статус шаблона")

    editor = DocxBlockEditor(doc)
    assert editor.replace_block(
        ["Жалобы"],
        "Жалобы:",
        "нарушение сна\nАнамнез жизни: эта строка является частью жалоб пациента",
        PRIMARY_MARKERS,
    )
    assert editor.replace_block(
        ["Анамнез жизни"],
        "Анамнез жизни:",
        "реальный анамнез жизни пациента",
        PRIMARY_MARKERS,
    )

    lines = [paragraph.text for paragraph in doc.paragraphs]
    assert "Жалобы: нарушение сна" in lines, lines
    assert "Анамнез жизни: эта строка является частью жалоб пациента" in lines, lines
    assert "Анамнез жизни: реальный анамнез жизни пациента" in lines, lines
    assert "старый анамнез шаблона" not in lines, lines
    assert "Психический статус" in lines, lines
    assert "старый психический статус шаблона" in lines, lines


def _assert_alias_boundary_stops_destructive_span_deletion() -> None:
    doc = Document()
    doc.add_paragraph("Жалобы при поступлении")
    doc.add_paragraph("старый текст жалоб")
    doc.add_paragraph("Психический статус")
    doc.add_paragraph("старый текст психического статуса")
    doc.add_paragraph("Диагноз")
    doc.add_paragraph("старый диагноз")

    editor = DocxBlockEditor(doc)
    assert editor.replace_block(
        ["Жалобы при поступлении"],
        "Жалобы при поступлении:",
        "новые жалобы",
        DISCHARGE_MARKERS,
    )

    lines = [paragraph.text for paragraph in doc.paragraphs]
    assert "Жалобы при поступлении: новые жалобы" in lines, lines
    assert "старый текст жалоб" not in lines, lines
    assert "Психический статус" in lines, lines
    assert "старый текст психического статуса" in lines, lines
    assert "Диагноз" in lines, lines


def verify() -> None:
    _assert_alias_coverage()
    _assert_inserted_marker_like_patient_text_never_becomes_structure()
    _assert_alias_boundary_stops_destructive_span_deletion()
    print("DOCX BLOCK BOUNDARY REGRESSION OK")


if __name__ == "__main__":
    verify()
