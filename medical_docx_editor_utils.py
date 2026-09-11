from __future__ import annotations

import re
from typing import Callable, Iterable, Sequence

from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from docx.shared import RGBColor

from medical_text_utils import normalize_match


def paragraph_matches_marker(normalized_paragraph_text: str, marker: str) -> bool:
    marker = normalize_match(marker)
    if not marker or not normalized_paragraph_text:
        return False
    text = normalized_paragraph_text.lstrip()
    if text.startswith(marker):
        if len(text) == len(marker):
            return True
        # Важно: короткие маркеры вроде «ЭПИ» не должны срабатывать на «ЭПИКРИЗ».
        # Разрешаем совпадение только если после маркера идёт разделитель.
        next_char = text[len(marker)]
        return not (next_char.isalnum() or next_char == "_")
    if marker == "зарегистрирован по адресу" and " зарегистрирован по адресу" in text:
        return True
    return False

def set_paragraph_font_color(paragraph: Paragraph, color: RGBColor) -> None:
    """Set an explicit final font color on every run of one output paragraph."""
    for run in paragraph.runs:
        run.font.color.rgb = color


def set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """Replace paragraph text while retaining the first run's direct formatting.

    Callers that only replace a substring should prefer
    ``replace_paragraph_regex_preserving_runs`` so unaffected runs/styles stay
    byte-for-byte represented in the document model.
    """
    if paragraph.runs:
        first = paragraph.runs[0]
        first.text = text
        for run in paragraph.runs[1:]:
            run.text = ""
        return
    paragraph.add_run(text)


def replace_paragraph_regex_preserving_runs(
    paragraph: Paragraph,
    pattern: str | re.Pattern[str],
    replacement: str | Callable[[re.Match[str]], str],
    *,
    flags: int = 0,
) -> int:
    """Regex-replace paragraph text without flattening unaffected Word runs.

    Replacements are applied from right to left.  Text inserted for a match
    inherits the direct formatting of the run where the match begins; all
    unaffected runs keep their original formatting.
    """
    runs = list(paragraph.runs)
    if not runs:
        return 0
    full_text = "".join(run.text for run in runs)
    regex = re.compile(pattern, flags) if isinstance(pattern, str) else pattern
    matches = list(regex.finditer(full_text))
    if not matches:
        return 0

    spans: list[tuple[int, int]] = []
    cursor = 0
    for run in runs:
        end = cursor + len(run.text)
        spans.append((cursor, end))
        cursor = end

    for match in reversed(matches):
        start, end = match.span()
        if start == end:
            continue
        first_idx = next((i for i, (_a, b) in enumerate(spans) if b > start), len(runs) - 1)
        last_idx = next((i for i, (a, _b) in enumerate(spans) if a >= end), len(runs)) - 1
        last_idx = max(first_idx, last_idx)
        first_start, _first_end = spans[first_idx]
        last_start, _last_end = spans[last_idx]
        before = runs[first_idx].text[: max(0, start - first_start)]
        after = runs[last_idx].text[max(0, end - last_start):]
        repl_text = replacement(match) if callable(replacement) else match.expand(replacement)
        if first_idx == last_idx:
            runs[first_idx].text = before + repl_text + after
        else:
            runs[first_idx].text = before + repl_text
            for idx in range(first_idx + 1, last_idx):
                runs[idx].text = ""
            runs[last_idx].text = after
    return len(matches)

def insert_paragraph_after(paragraph: Paragraph, text: str = "") -> Paragraph:
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    new_para = Paragraph(new_p, paragraph._parent)
    if text:
        new_para.add_run(text)
    return new_para

def remove_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)

def iter_all_paragraphs(parent) -> Iterable[Paragraph]:
    """Все абзацы документа, включая абзацы внутри таблиц."""
    if isinstance(parent, DocxDocument):
        for paragraph in parent.paragraphs:
            yield paragraph
        for table in parent.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from iter_all_paragraphs(cell)
    elif isinstance(parent, _Cell):
        for paragraph in parent.paragraphs:
            yield paragraph
        for table in parent.tables:
            for row in table.rows:
                for cell in row.cells:
                    yield from iter_all_paragraphs(cell)

def remove_exact_paragraphs(doc: DocxDocument, values: Sequence[str]) -> int:
    """Remove standalone service paragraphs such as a trailing 'ЭЭГ'."""
    normalized_values = {normalize_match(value) for value in values}
    count = 0
    for paragraph in list(iter_all_paragraphs(doc)):
        if normalize_match(paragraph.text) in normalized_values:
            remove_paragraph(paragraph)
            count += 1
    return count
