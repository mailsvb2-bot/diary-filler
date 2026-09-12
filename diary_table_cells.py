"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import re
from datetime import date

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from diary_constants import DIARY_SIGNATURE_GAP_LINES, HOLIDAY_SKIP_END_DAY, HOLIDAY_SKIP_MONTHS, HOLIDAY_SKIP_START_DAY, STATUS_FONT_SIZE_PT, STRUCTURAL_DIARY_PREFIXES
from diary_dates import add_month, format_month_year, parse_month_year, safe_row_date
from diary_text_parser import is_signature_paragraph_text, normalize_text, remove_examinee_words

def clear_paragraph_keep_properties(paragraph) -> None:
    p = paragraph._p
    for child in list(p):
        if child.tag.endswith("}pPr"):
            continue
        p.remove(child)

def reset_cell_to_one_paragraph(cell):
    if not cell.paragraphs:
        return cell.add_paragraph()
    first = cell.paragraphs[0]
    clear_paragraph_keep_properties(first)
    for paragraph in list(cell.paragraphs[1:]):
        paragraph._element.getparent().remove(paragraph._element)
    return first

def is_structural_diary_prefix(text: str) -> bool:
    """Return True for template notes that should stay above generated diary text."""
    low = normalize_text(text).lower().replace("ё", "е")
    return any(low.startswith(prefix) for prefix in STRUCTURAL_DIARY_PREFIXES)

def first_signature_paragraph_index(cell) -> int | None:
    for index, paragraph in enumerate(cell.paragraphs):
        if is_signature_paragraph_text(paragraph.text):
            return index
    return None

def add_run_with_size(paragraph, text: str):
    run = paragraph.add_run(text)
    run.font.size = Pt(STATUS_FONT_SIZE_PT)
    return run

def fill_text_cell(cell, text: str, *, alignment=None) -> None:
    paragraph = reset_cell_to_one_paragraph(cell)
    if alignment is not None:
        paragraph.alignment = alignment
    add_run_with_size(paragraph, text)

def write_diary_text_into_existing_paragraph(paragraph, diary_text: str) -> None:
    clear_paragraph_keep_properties(paragraph)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_run_with_size(paragraph, diary_text)

def _format_paragraphs(paragraphs) -> None:
    items = list(paragraphs)
    for paragraph in items:
        for run in paragraph.runs:
            run.font.size = Pt(STATUS_FONT_SIZE_PT)
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)

    for index, paragraph in enumerate(items):
        if not is_signature_paragraph_text(paragraph.text):
            continue
        next_nonempty = None
        blank_paragraphs_after = []
        for candidate in items[index + 1 :]:
            if not normalize_text(candidate.text):
                blank_paragraphs_after.append(candidate)
                continue
            next_nonempty = candidate
            break
        if next_nonempty is None or not is_signature_paragraph_text(next_nonempty.text):
            # Guarantee at most three compact blank-line equivalents between
            # the last signature and the next diary. Some legacy templates carry
            # many physical empty paragraphs; keeping them would defeat a smaller
            # ``space_after`` value, so remove only the excess empty paragraphs.
            for extra in blank_paragraphs_after[DIARY_SIGNATURE_GAP_LINES:]:
                parent = extra._p.getparent()
                if parent is not None:
                    parent.remove(extra._p)
            visible_blank_lines = min(len(blank_paragraphs_after), DIARY_SIGNATURE_GAP_LINES)
            remaining_lines = max(0, DIARY_SIGNATURE_GAP_LINES - visible_blank_lines)
            paragraph.paragraph_format.space_after = Pt(STATUS_FONT_SIZE_PT * remaining_lines)


def apply_compact_diary_layout(doc: DocxDocument) -> None:
    """Apply the doctor's compact print layout to every diary output mode."""
    for section in doc.sections:
        section.left_margin = Cm(1.5)
        section.right_margin = Cm(1.0)
        section.top_margin = Cm(1.0)
        section.bottom_margin = Cm(1.0)

    try:
        doc.styles["Normal"].font.size = Pt(STATUS_FONT_SIZE_PT)
    except KeyError:
        pass

    _format_paragraphs(doc.paragraphs)
    # Do not deduplicate by ``id(cell._tc)``: python-docx can create transient
    # wrappers whose Python ids are reused while iterating a table. Reformatting
    # a merged cell twice is harmless; accidentally skipping a real cell is not.
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                _format_paragraphs(cell.paragraphs)
