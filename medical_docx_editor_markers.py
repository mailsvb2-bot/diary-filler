from __future__ import annotations

from typing import Optional, Sequence

from medical_text_utils import normalize_match
from medical_docx_editor_utils import paragraph_matches_marker


class DocxEditorMarkersMixin:
    def find_paragraph_index(self, markers: Sequence[str]) -> Optional[int]:
        for i, paragraph in enumerate(self.paragraphs):
            text = normalize_match(paragraph.text)
            if any(paragraph_matches_marker(text, marker) for marker in markers):
                return i
        return None

    def find_next_marker_index(self, start: int, markers: Sequence[str], *, exclude: Sequence[str] = ()) -> Optional[int]:
        excluded = {normalize_match(m) for m in exclude}
        for i, paragraph in enumerate(self.paragraphs[start:], start=start):
            text = normalize_match(paragraph.text)
            if not text:
                continue
            for marker in markers:
                norm_marker = normalize_match(marker)
                if norm_marker in excluded:
                    continue
                if paragraph_matches_marker(text, marker):
                    return i
        return None
