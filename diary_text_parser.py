"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from diary_constants import (DATE_PREFIX_RE, EXAMINEE_ANY_RE, EXAMINEE_STANDARD_STATE_RE, EXAMINEE_START_RE, MIN_STATUS_LEN, SIGNATURE_MARKERS, STATUS_DATE_PREFIX_RE, STATUS_LABEL_PREFIX_RE, STATUS_NUMBER_BEFORE_DATE_RE, STATUS_NUMBER_PREFIX_RE, STATUS_STANDALONE_DAY_PREFIX_RE, STRUCTURAL_DIARY_PREFIXES, WHITESPACE_RE)

def normalize_text(text: str) -> str:
    text = (text or "")
    text = re.sub(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]", "", text)
    text = text.replace("\xa0", " ").replace("\n", " ")
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def strip_leading_status_metadata(text: str) -> str:
    value = normalize_text(text)
    patterns = (
        STATUS_LABEL_PREFIX_RE,
        STATUS_NUMBER_BEFORE_DATE_RE,
        STATUS_DATE_PREFIX_RE,
        DATE_PREFIX_RE,
        STATUS_NUMBER_PREFIX_RE,
        STATUS_STANDALONE_DAY_PREFIX_RE,
    )
    for _ in range(12):
        before = value
        for pattern in patterns:
            updated = pattern.sub("", value, count=1).lstrip(" —-–—:.);,]\t")
            if updated != value:
                value = normalize_text(updated)
                break
        if value == before:
            break
    return normalize_text(value)


def remove_examinee_words(text: str) -> str:
    value = normalize_text(text)
    value = EXAMINEE_STANDARD_STATE_RE.sub(lambda match: match.group(1), value)
    for _ in range(3):
        updated = EXAMINEE_START_RE.sub("", value)
        if updated == value:
            break
        value = normalize_text(updated)
    value = EXAMINEE_ANY_RE.sub("", value)
    value = re.sub(r"^\s*[:,.;!\-–—]+\s*", "", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([\(\[\{])\s+", r"\1", value)
    value = re.sub(r"\s+([\)\]\}])", r"\1", value)
    value = re.sub(r"\s{2,}", " ", value)
    return normalize_text(value)


def clean_status_text(text: str) -> str:
    return remove_examinee_words(strip_leading_status_metadata(text))


def is_signature_paragraph_text(text: str) -> bool:
    """Return True for template signature paragraphs that must stay untouched."""
    low = normalize_text(text).lower().replace("ё", "е")
    return any(low.startswith(marker) for marker in SIGNATURE_MARKERS)


def looks_like_status(text: str) -> bool:
    text = clean_status_text(text)
    low = text.lower()
    if len(text) < MIN_STATUS_LEN:
        return False
    if is_signature_paragraph_text(text):
        return False
    if any(low.startswith(prefix) for prefix in STRUCTURAL_DIARY_PREFIXES):
        return False
    if low in {"дневник наблюдения", "день госпитализации", "число", "дата", "месяц/год", "месяц / год"}:
        return False
    if re.fullmatch(r"[\d\s./-]+", text):
        return False
    return True


def _convert_legacy_doc_to_docx(source: Path, target: Path) -> None:
    """Convert a legacy binary .doc using Microsoft Word on Windows.

    python-docx cannot read the old OLE .doc format. The desktop application
    already depends on pywin32 on Windows, so we convert into a temporary DOCX
    and then run the exact same tested parser used for native DOCX files.
    """
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
        # wdFormatXMLDocument == 12. SaveAs2 preserves the document while making
        # it readable by python-docx; the user's original .doc is never modified.
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


def _open_status_document(path: Path):
    if path.suffix.lower() != ".doc":
        return Document(str(path)), None
    temp = TemporaryDirectory(prefix="medical-autofill-legacy-doc-")
    converted = Path(temp.name) / (path.stem + ".docx")
    try:
        _convert_legacy_doc_to_docx(path, converted)
        return Document(str(converted)), temp
    except Exception:
        temp.cleanup()
        raise


def extract_statuses_from_docx(path: str | Path, *, deduplicate: bool = True) -> list[str]:
    source = Path(path)
    doc, temporary_conversion = _open_status_document(source)
    statuses: list[str] = []
    seen_statuses: set[str] = set()

    def add_candidate(text: str) -> None:
        cleaned = clean_status_text(text)
        key = cleaned.lower().replace("ё", "е")
        if looks_like_status(cleaned) and (not deduplicate or key not in seen_statuses):
            statuses.append(cleaned)
            if deduplicate:
                seen_statuses.add(key)

    try:
        for paragraph in doc.paragraphs:
            add_candidate(paragraph.text)
        for table in doc.tables:
            for row in table.rows:
                seen_cells: set[int] = set()
                for cell in row.cells:
                    # Merged cells are exposed repeatedly by python-docx; process each
                    # physical cell once so one diary text does not consume several rows.
                    tc_id = id(cell._tc)
                    if tc_id in seen_cells:
                        continue
                    seen_cells.add(tc_id)
                    for paragraph in cell.paragraphs:
                        add_candidate(paragraph.text)
        return statuses
    finally:
        if temporary_conversion is not None:
            temporary_conversion.cleanup()
