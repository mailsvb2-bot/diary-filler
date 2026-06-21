"""Разделённый слой заполнителя дневников.

Файл создан при архитектурной нарезке бывшего diary_filler.py.
"""

from __future__ import annotations

from pathlib import Path

from diary_constants import INVALID_FILENAME_CHARS_RE, WHITESPACE_RE
from diary_text_parser import normalize_text

def safe_filename_part(text: str) -> str:
    value = normalize_text(text)
    value = INVALID_FILENAME_CHARS_RE.sub(" ", value)
    value = WHITESPACE_RE.sub(" ", value).strip(" .")
    if not value:
        raise ValueError("Введите ФИО пациента")
    value = value[:120].strip(" .")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    stem_for_reserved_check = value.split(".", 1)[0].upper()
    if stem_for_reserved_check in reserved:
        value = f"{value}_"
    return value


def make_diary_output_name(patient_name: str, *, file_index: int, total_files: int) -> str:
    base = f"{patient_name} дневники"
    if total_files > 1:
        base = f"{base} {file_index:02d}"
    return f"{base}.docx"


def available_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.with_suffix("")
    ext = path.suffix
    for idx in range(2, 10000):
        candidate = Path(f"{stem}_{idx}{ext}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Не удалось подобрать имя файла для {path}")
