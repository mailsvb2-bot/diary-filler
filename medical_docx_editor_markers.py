from __future__ import annotations

from typing import Optional, Sequence

from medical_text_utils import normalize_match
from medical_docx_editor_utils import paragraph_matches_marker


class DocxEditorMarkersMixin:
    def find_paragraph_index(self, markers: Sequence[str]) -> Optional[int]:
        for i, paragraph in enumerate(self.paragraphs):
            template_text = self.template_paragraph_text(paragraph)
            if template_text is None:
                # Paragraphs created from patient data are content, never template structure.
                continue
            current_text = normalize_match(paragraph.text)
            if any(
                paragraph_matches_marker(template_text, marker)
                or paragraph_matches_marker(current_text, marker)
                for marker in markers
            ):
                return i
        return None

    def find_next_marker_index(self, start: int, markers: Sequence[str], *, exclude: Sequence[str] = ()) -> Optional[int]:
        excluded = {normalize_match(m) for m in exclude}
        for i, paragraph in enumerate(self.paragraphs[start:], start=start):
            template_text = self.template_paragraph_text(paragraph)
            if not template_text:
                continue
            for marker in markers:
                norm_marker = normalize_match(marker)
                if norm_marker in excluded:
                    continue
                if paragraph_matches_marker(template_text, marker):
                    return i
        return None
