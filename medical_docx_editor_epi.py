from __future__ import annotations

import re

from docx.document import Document as DocxDocument

from medical_docx_editor_utils import iter_all_paragraphs, remove_paragraph, set_paragraph_text


EPI_WORD_RE = re.compile(r"(?<![A-Za-zА-ЯЁа-яё])ЭПИ(?![A-Za-zА-ЯЁа-яё])", re.IGNORECASE)


def remove_epi_from_text(text: str) -> str:
    """Удаляет именно слово/аббревиатуру «ЭПИ», не трогая «ЭПИКРИЗ»."""
    cleaned = EPI_WORD_RE.sub("", text or "")
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    cleaned = re.sub(r",\s*,+", ", ", cleaned)
    cleaned = re.sub(r":\s*,\s*", ": ", cleaned)
    cleaned = re.sub(r",\s*([.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"[-–—:]\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()

def remove_epi_mentions_from_document(doc: DocxDocument) -> None:
    """Если ЭПИ-файл не выбран, удаляет все видимые упоминания ЭПИ из результата."""
    for paragraph in list(iter_all_paragraphs(doc)):
        text = paragraph.text
        if not EPI_WORD_RE.search(text or ""):
            continue
        cleaned = remove_epi_from_text(text)
        if cleaned.strip(" ,.;:-–—()"):
            set_paragraph_text(paragraph, cleaned)
        else:
            remove_paragraph(paragraph)
