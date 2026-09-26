"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
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
_DOCX_STORY_BOUNDARY = "__DOCX_STORY_BOUNDARY__"

_LEGACY_DOC_CACHE_LOCK = threading.Lock()
_LEGACY_DOC_CACHE_CONTEXT: TemporaryDirectory | None = None
_LEGACY_DOC_CACHE: dict[tuple[str, int, int], Path] = {}
_LEGACY_DOC_CACHE_MAX_ENTRIES = 4


def _active_word_hwnd(win32com_client) -> int | None:
    """Return the existing user's Word window handle when COM exposes it."""
    try:
        active = win32com_client.GetActiveObject("Word.Application")
        hwnd = int(getattr(active, "Hwnd", 0) or 0)
        return hwnd or None
    except Exception:
        return None


def _word_automation_safe_to_quit(
    *,
    preexisting_user_hwnd: int | None,
    automation_hwnd: int | None,
    user_control: bool,
    visible: bool,
    document_count: int,
) -> bool:
    """Return True only when the Word instance is still provably automation-only."""
    if automation_hwnd is None:
        return False
    if preexisting_user_hwnd is not None and automation_hwnd == preexisting_user_hwnd:
        return False
    if user_control or visible or document_count != 0:
        return False
    return True


def _word_automation_snapshot(word) -> tuple[int | None, bool, bool, int] | None:
    """Read ownership-sensitive Word state conservatively; ambiguity means no Quit."""
    try:
        hwnd = int(getattr(word, "Hwnd", 0) or 0) or None
        user_control = bool(getattr(word, "UserControl", True))
        visible = bool(getattr(word, "Visible", True))
        document_count = int(getattr(word.Documents, "Count", 0) or 0)
    except Exception:
        return None
    return hwnd, user_control, visible, document_count


def _legacy_doc_cache_path(source: Path) -> Path:
    """Convert one exact .doc filesystem revision at most once per process."""
    global _LEGACY_DOC_CACHE_CONTEXT

    resolved = source.resolve()
    stat = resolved.stat()
    key = (str(resolved), int(stat.st_size), int(stat.st_mtime_ns))
    with _LEGACY_DOC_CACHE_LOCK:
        cached = _LEGACY_DOC_CACHE.get(key)
        if cached is not None and cached.is_file():
            return cached

        if _LEGACY_DOC_CACHE_CONTEXT is None:
            _LEGACY_DOC_CACHE_CONTEXT = TemporaryDirectory(
                prefix="medical-autofill-legacy-doc-cache-"
            )
        digest = hashlib.sha256(
            f"{key[0]}|{key[1]}|{key[2]}".encode("utf-8", errors="surrogatepass")
        ).hexdigest()[:24]
        target = Path(_LEGACY_DOC_CACHE_CONTEXT.name) / f"{digest}.docx"
        convert_legacy_doc_to_docx(resolved, target)
        _LEGACY_DOC_CACHE[key] = target

        while len(_LEGACY_DOC_CACHE) > _LEGACY_DOC_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(_LEGACY_DOC_CACHE))
            old_path = _LEGACY_DOC_CACHE.pop(oldest_key)
            if old_path != target:
                try:
                    old_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return target


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
    user_word_hwnd = None
    automation_word_hwnd = None
    pythoncom.CoInitialize()
    try:
        # Word is a user application. Never assume that a COM object belongs to
        # us merely because we requested DispatchEx: record the already-active
        # user instance and refuse to Quit it if COM returns that same window.
        user_word_hwnd = _active_word_hwnd(win32com.client)
        word = win32com.client.DispatchEx("Word.Application")
        try:
            automation_word_hwnd = int(getattr(word, "Hwnd", 0) or 0) or None
        except Exception:
            automation_word_hwnd = None
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
            opened = None
        if word is not None:
            # A user can launch Word while our hidden conversion instance still
            # exists. Word may then expose that same COM instance interactively.
            # Re-check ownership after closing our document and again after a
            # short grace period. If Word became visible/user-controlled or has
            # any document, release our COM reference without calling Quit().
            distinct_from_preexisting_user = bool(
                user_word_hwnd is None
                or (
                    automation_word_hwnd is not None
                    and automation_word_hwnd != user_word_hwnd
                )
            )
            snapshot = _word_automation_snapshot(word)
            safe_to_quit = bool(
                distinct_from_preexisting_user
                and snapshot is not None
                and _word_automation_safe_to_quit(
                    preexisting_user_hwnd=user_word_hwnd,
                    automation_hwnd=snapshot[0] or automation_word_hwnd,
                    user_control=snapshot[1],
                    visible=snapshot[2],
                    document_count=snapshot[3],
                )
            )
            if safe_to_quit:
                try:
                    pythoncom.PumpWaitingMessages()
                except Exception:
                    pass
                time.sleep(0.15)
                snapshot = _word_automation_snapshot(word)
                safe_to_quit = bool(
                    snapshot is not None
                    and _word_automation_safe_to_quit(
                        preexisting_user_hwnd=user_word_hwnd,
                        automation_hwnd=snapshot[0] or automation_word_hwnd,
                        user_control=snapshot[1],
                        visible=snapshot[2],
                        document_count=snapshot[3],
                    )
                )
            if safe_to_quit:
                try:
                    word.Quit()
                except Exception:
                    pass
            # Release the COM proxy while COM is still initialized.  In the
            # user-took-ownership path this is what prevents our process from
            # keeping Word alive or making the next launch sluggish.
            word = None
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
    # One primary .doc is consulted by several canonical readers (classification,
    # parser, title-date lookup). Reuse one exact conversion instead of repeatedly
    # starting and stopping Microsoft Word during the same GUI session.
    yield _legacy_doc_cache_path(source)


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
    elif hasattr(parent, "_element"):
        # Header/footer story objects expose their XML root as _element.
        parent_elm = parent._element
    else:
        return

    for child in parent_elm.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("}tbl"):
            yield Table(child, parent)


def _xml_local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _text_container_lines(element) -> list[str]:
    """Extract text stored in Word text boxes / drawing shape text containers."""
    result: list[str] = []
    for container in element.iter():
        if _xml_local_name(container.tag) not in {"txbxContent", "txBody"}:
            continue
        for paragraph in container.iter():
            if _xml_local_name(paragraph.tag) != "p":
                continue
            chunks: list[str] = []
            for node in paragraph.iter():
                name = _xml_local_name(node.tag)
                if name == "t" and node.text:
                    chunks.append(node.text)
                elif name == "tab":
                    chunks.append("\t")
                elif name in {"br", "cr"}:
                    chunks.append("\n")
            value = normalize_text("".join(chunks)).strip()
            if value:
                result.append(value)
    return result


def extract_docx_text(path: str | Path) -> str:
    candidate = Path(path).expanduser()
    cached_text, before_signature = _docx_text_cache_lookup(candidate)
    if cached_text is not None:
        return cached_text

    lines: List[str] = []

    def walk(parent):
        for block in iter_block_items(parent):
            if isinstance(block, Paragraph):
                paragraph_text = block.text
                lines.append(paragraph_text)
                normalized_paragraph = normalize_text(paragraph_text)
                for shape_text in _text_container_lines(block._p):
                    # python-docx normally omits text-box text from Paragraph.text.
                    # If a future version exposes it, avoid duplicating the same text.
                    if shape_text not in normalized_paragraph:
                        lines.append(shape_text)
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

        # Headers/footers are independent Word "stories". Append each unique part
        # behind an explicit parser boundary so footer/header text can never become
        # the tail of the last clinical block in the document body.
        seen_story_parts: set[str] = set()
        for section in doc.sections:
            for story in (
                section.header,
                section.first_page_header,
                section.even_page_header,
                section.footer,
                section.first_page_footer,
                section.even_page_footer,
            ):
                try:
                    part_key = str(story.part.partname)
                except Exception:
                    part_key = str(id(story._element))
                if part_key in seen_story_parts:
                    continue
                seen_story_parts.add(part_key)
                story_lines: list[str] = []
                previous_lines = lines
                lines = story_lines
                try:
                    walk(story)
                    for shape_text in _text_container_lines(story._element):
                        if shape_text not in "\n".join(story_lines):
                            story_lines.append(shape_text)
                finally:
                    lines = previous_lines
                if any(normalize_text(item).strip() for item in story_lines):
                    lines.append(_DOCX_STORY_BOUNDARY)
                    lines.extend(story_lines)

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
