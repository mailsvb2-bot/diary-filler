from __future__ import annotations

from typing import List

from docx.document import Document as DocxDocument
from docx.text.paragraph import Paragraph

from medical_text_utils import normalize_match


class DocxEditorCoreMixin:
    def __init__(self, doc: DocxDocument):
        self.doc = doc
        # Keep the structural identity of paragraphs that came from the template.
        # Patient text inserted later must never become a new section marker.
        self._template_paragraph_text_by_id = {
            id(paragraph._p): normalize_match(paragraph.text)
            for paragraph in doc.paragraphs
        }

    @property
    def paragraphs(self) -> List[Paragraph]:
        return list(self.doc.paragraphs)

    def template_paragraph_text(self, paragraph: Paragraph) -> str | None:
        return self._template_paragraph_text_by_id.get(id(paragraph._p))
