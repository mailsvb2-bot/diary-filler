"""Facade for low-level DOCX editing helpers."""
from __future__ import annotations

from medical_docx_editor_core import DocxEditorCoreMixin
from medical_docx_editor_epi import EPI_WORD_RE, remove_epi_from_text, remove_epi_mentions_from_document
from medical_docx_editor_markers import DocxEditorMarkersMixin
from medical_docx_editor_replace import DocxEditorReplaceMixin
from medical_docx_editor_utils import (
    insert_paragraph_after,
    iter_all_paragraphs,
    paragraph_matches_marker,
    remove_exact_paragraphs,
    remove_paragraph,
    set_paragraph_text,
)


class DocxBlockEditor(DocxEditorCoreMixin, DocxEditorReplaceMixin, DocxEditorMarkersMixin):
    pass


__all__ = [
    "DocxBlockEditor",
    "paragraph_matches_marker",
    "set_paragraph_text",
    "insert_paragraph_after",
    "remove_paragraph",
    "remove_exact_paragraphs",
    "iter_all_paragraphs",
    "remove_epi_from_text",
    "remove_epi_mentions_from_document",
    "EPI_WORD_RE",
]
