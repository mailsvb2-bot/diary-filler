"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import os
import re
import threading
import zipfile
from contextlib import contextmanager
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, List, Optional

from docx import Document
from docx.document import Document as DocxDocument
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from medical_constants import DATE_FMT
from medical_text_utils import normalize_match, normalize_text


_DOCX_TEXT_CACHE_MAX_ENTRIES = 8
_DOCX_TEXT_CACHE_LOCK = threading.Lock()
_DOCX_TEXT_CACHE: dict[str, tuple[int, int, str]] = {}


_SUPPORTED_WORD_SUFFIXES = {".doc", ".docx", ".docm"}


def convert_legacy_doc_to_docx(source: Path, target: Path) -> None:
    """Convert old binary Word .doc into a temporary DOCX without touching source."""
    if os.name != "nt":
        raise ValueError(
            "Старый формат .doc поддерживается в установленной Windows-программе через Microsoft Word. "
            "На этой системе сохраните файл как .docx."
        )
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise ValueError(
            "Не удалось подключить поддержку .doc через Microsoft Word. "
            "Сохраните файл как .docx или переустановите программу."
        ) from exc

    word = None
    opened = None
    pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        opened = word.Documents.Open(
            str(source.resolve()),
            ReadOnly=True,
            AddToRecentFiles=False,
            ConfirmConversions=False,
        )
        # wdFormatXMLDocument == 12. The original .doc remains unchanged.
        opened.SaveAs2(str(target.resolve()), FileFormat=12, AddToRecentFiles=False)
    except Exception as exc:
        raise ValueError(
            f"Не удалось прочитать старый Word-файл .doc: {source.name}. "
            "Для .doc требуется установленный Microsoft Word; можно также сохранить файл как .docx."
        ) from exc
    finally:
        if opened is not None:
            try:
                opened.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


@contextmanager
def materialize_word_source_as_docx(path: str | Path):
    """Yield a python-docx-readable path for .docx/.docm/.doc inputs."""
    source = Path(path).expanduser()
    suffix = source.suffix.lower()
    if suffix not in _SUPPORTED_WORD_SUFFIXES:
        allowed = ", ".join(sorted(_SUPPORTED_WORD_SUFFIXES))
        raise ValueError(f"Неверный формат Word-файла: {suffix or 'без расширения'}. Разрешено: {allowed}.")
    if suffix != ".doc":
        yield source
        return
    with TemporaryDirectory(prefix="medical-autofill-legacy-doc-") as tmp_dir:
        converted = Path(tmp_dir) / (source.stem + ".docx")
        convert_legacy_doc_to_docx(source, converted)
        yield converted


def _docx_text_cache_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):
        return str(path.absolute())


def _docx_text_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _docx_text_cache_lookup(path: Path) -> tuple[str | None, tuple[int, int] | None]:
    """Return cached text only while path, size and nanosecond mtime stay exact."""
    try:
        before = _docx_text_signature(path)
    except OSError:
        return None, None

    key = _docx_text_cache_key(path)
    with _DOCX_TEXT_CACHE_LOCK:
        entry = _DOCX_TEXT_CACHE.get(key)
        if entry is None:
            return None, before
        if entry[:2] != before:
            _DOCX_TEXT_CACHE.pop(key, None)
            return None, before
        cached_text = entry[2]

    # Re-check after the lookup so a file that changes while we inspect the
    # cache can never be returned from the old entry.
    try:
        after = _docx_text_signature(path)
    except OSError:
        return None, None
    if after != before:
        with _DOCX_TEXT_CACHE_LOCK:
            _DOCX_TEXT_CACHE.pop(key, None)
        return None, after
    return cached_text, before


def _docx_text_cache_store(path: Path, signature: tuple[int, int], text: str) -> None:
    key = _docx_text_cache_key(path)
    with _DOCX_TEXT_CACHE_LOCK:
        # Refresh insertion order for the bounded process-local cache.
        _DOCX_TEXT_CACHE.pop(key, None)
        _DOCX_TEXT_CACHE[key] = (signature[0], signature[1], text)
        while len(_DOCX_TEXT_CACHE) > _DOCX_TEXT_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(_DOCX_TEXT_CACHE))
            _DOCX_TEXT_CACHE.pop(oldest_key, None)


def _docx_text_cache_invalidate(path: Path) -> None:
    key = _docx_text_cache_key(path)
    with _DOCX_TEXT_CACHE_LOCK:
        _DOCX_TEXT_CACHE.pop(key, None)


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
    candidate = Path(path).expanduser()
    cached_text, before_signature = _docx_text_cache_lookup(candidate)
    if cached_text is not None:
        return cached_text

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

    with materialize_word_source_as_docx(candidate) as readable_path:
        doc = Document(str(readable_path))
        walk(doc)
    text = normalize_text("\n".join(lines))

    # Cache only a stable read. If Word/Explorer modified or replaced the file
    # while python-docx was opening it, the next caller must perform a real read.
    if before_signature is not None:
        try:
            after_signature = _docx_text_signature(candidate)
        except OSError:
            after_signature = None
        if after_signature == before_signature:
            _docx_text_cache_store(candidate, before_signature, text)
        else:
            _docx_text_cache_invalidate(candidate)

    return text
