"""Shared filename and collision-path primitives for generated documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE_RE = re.compile(r"\s+")
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(
    value: str,
    *,
    normalizer: Callable[[str], str],
    max_length: int,
    default: str | None = None,
    empty_error: str | None = None,
) -> str:
    """Sanitize one Windows filename stem while preserving caller policy."""
    text = normalizer(value)
    if not text and default is not None:
        text = default
    text = _INVALID_FILENAME_CHARS_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" .")
    text = text[:max_length].strip(" .")
    if not text:
        if default is not None:
            text = default
        elif empty_error is not None:
            raise ValueError(empty_error)
        else:
            raise ValueError("Пустое имя файла")
    if text.split(".", 1)[0].upper() in _RESERVED_NAMES:
        text = f"{text}_"
    return text


def resolve_available_path(path: Path, *, style: str) -> Path:
    """Return a free sibling path using the caller's historical suffix style."""
    if not path.exists():
        return path
    stem = path.with_suffix("")
    ext = path.suffix
    for index in range(2, 10000):
        if style == "paren":
            candidate = Path(f"{stem} ({index}){ext}")
        elif style == "underscore":
            candidate = Path(f"{stem}_{index}{ext}")
        else:
            raise ValueError(f"Неизвестный стиль имени при коллизии: {style}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Не удалось подобрать имя файла для {path}")


def _diary_normalize_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]", "", text)
    text = text.replace("\xa0", " ").replace("\n", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def safe_filename_part(text: str) -> str:
    """Backward-compatible diary filename policy."""
    return sanitize_filename(
        text, normalizer=_diary_normalize_text, max_length=120,
        empty_error="Введите ФИО пациента",
    )


def make_diary_output_name(patient_name: str, *, file_index: int, total_files: int) -> str:
    base = f"{patient_name} дневники"
    if total_files > 1:
        base = f"{base} {file_index:02d}"
    return f"{base}.docx"


def available_path(path: Path) -> Path:
    """Backward-compatible diary collision policy."""
    return resolve_available_path(path, style="underscore")
