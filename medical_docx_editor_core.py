from __future__ import annotations

from typing import List

from docx.document import Document as DocxDocument
from docx.text.paragraph import Paragraph


class DocxEditorCoreMixin:
    def __init__(self, doc: DocxDocument):
        self.doc = doc

    @property
    def paragraphs(self) -> List[Paragraph]:
        return list(self.doc.paragraphs)
