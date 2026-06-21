"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from docx import Document
from docx.document import Document as DocxDocument
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from medical_constants import DATE_FMT
from medical_text_utils import normalize_match, normalize_text

def iter_block_items(parent) -> Iterable[Paragraph | Table]:
    if isinstance(parent, DocxDocument):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        return

    for child in parent_elm.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def extract_docx_text(path: str | Path) -> str:
    doc = Document(str(path))
    lines: List[str] = []

    def walk(parent):
        for block in iter_block_items(parent):
            if isinstance(block, Paragraph):
                lines.append(block.text)
            elif isinstance(block, Table):
                for row in block.rows:
                    seen_cells: set[int] = set()
                    for cell in row.cells:
                        # python-docx returns the same merged cell multiple times.
                        # Without this guard parsed text and diary statuses can be duplicated.
                        tc_id = id(cell._tc)
                        if tc_id in seen_cells:
                            continue
                        seen_cells.add(tc_id)
                        walk(cell)

    walk(doc)
    return normalize_text("\n".join(lines))
