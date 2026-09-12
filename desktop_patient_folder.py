"""Patient work-folder naming for the optional desktop intake layer.

This module deliberately does not participate in document generation.  It only
reads the same primary DOCX the application already understands and builds a
safe Windows folder name for the episode workspace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from medical_parser import MedicalTextParser


FOLDER_NAMING_OPTIONS = {
    "full_fio": "ФИО полностью",
    "surname_initials": "Фамилия полностью, Имя и Отчество буквами",
    "surname_name": "Фамилия Имя",
    "admission_date": "Дата поступления",
    "discharge_date": "Дата выписки",
    "admission_discharge_dates": "Дата поступления и дата выписки",
    "admission_month": "Месяц поступления",
    "discharge_month": "Месяц выписки",
}

DEFAULT_FOLDER_NAMING_SETTINGS = {
    "parts": ["surname_initials", "admission_month"],
    "date_format": "short",
}

_RUSSIAN_MONTHS = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)

_INVALID_WINDOWS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True)
class PrimaryPatientFolderInfo:
    fio: str
    admission_date: str
    folder_name: str


def normalize_folder_naming_settings(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a validated, forward-compatible folder naming configuration."""
    source = dict(settings or {})
    raw_parts = source.get("parts", DEFAULT_FOLDER_NAMING_SETTINGS["parts"])
    if not isinstance(raw_parts, (list, tuple)):
        raw_parts = DEFAULT_FOLDER_NAMING_SETTINGS["parts"]
    parts: list[str] = []
    for value in raw_parts:
        key = str(value or "").strip()
        if key in FOLDER_NAMING_OPTIONS and key not in parts:
            parts.append(key)
    if not parts:
        parts = list(DEFAULT_FOLDER_NAMING_SETTINGS["parts"])

    date_format = str(source.get("date_format", "short") or "short").strip().lower()
    if date_format not in {"short", "full"}:
        date_format = "short"
    return {"parts": parts, "date_format": date_format}


def sanitize_folder_component(value: str, *, fallback: str = "Пациент", max_length: int = 120) -> str:
    """Make one human-readable Windows folder component without leaking elsewhere."""
    text = _INVALID_WINDOWS_CHARS_RE.sub(" ", str(value or ""))
    text = " ".join(text.split()).strip(" .")
    if not text:
        text = fallback
    if text.upper() in _WINDOWS_RESERVED_NAMES:
        text = f"_{text}"
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    return text or fallback


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)", text)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _format_date(value: Any, *, date_format: str) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%d.%m.%y" if date_format == "short" else "%d.%m.%Y")


def _format_month(value: Any) -> str:
    parsed = _parse_date(value)
    if not parsed:
        return ""
    return f"{_RUSSIAN_MONTHS[parsed.month - 1]} {parsed.year}"


def _fio_tokens(fio: str) -> list[str]:
    return [token for token in re.split(r"\s+", str(fio or "").strip()) if token]


def _surname_initials(fio: str) -> str:
    tokens = _fio_tokens(fio)
    if not tokens:
        return ""
    surname = tokens[0]
    initials = "".join(f"{token[0].upper()}." for token in tokens[1:3] if token)
    return f"{surname} {initials}".strip()


def _surname_name(fio: str) -> str:
    tokens = _fio_tokens(fio)
    return " ".join(tokens[:2])


def build_patient_folder_name(
    *,
    fio: str,
    admission_date: Any = "",
    discharge_date: Any = "",
    fallback_stem: str = "Пациент",
    settings: Mapping[str, Any] | None = None,
) -> str:
    """Build an episode folder name using Dokkomplekt-compatible naming parts.

    Intake uses the donor project's safe default: surname + initials and the
    admission month.  Discharge-dependent parts remain supported by the naming
    engine without forcing the intake layer to invent a discharge date.
    """
    config = normalize_folder_naming_settings(settings)
    date_format = str(config["date_format"])
    values = {
        "full_fio": str(fio or "").strip(),
        "surname_initials": _surname_initials(fio),
        "surname_name": _surname_name(fio),
        "admission_date": _format_date(admission_date, date_format=date_format),
        "discharge_date": _format_date(discharge_date, date_format=date_format),
        "admission_discharge_dates": " — ".join(
            part
            for part in (
                _format_date(admission_date, date_format=date_format),
                _format_date(discharge_date, date_format=date_format),
            )
            if part
        ),
        "admission_month": _format_month(admission_date),
        "discharge_month": _format_month(discharge_date),
    }
    selected = [values[key] for key in config["parts"] if values.get(key)]
    raw = " ".join(selected).strip() or str(fallback_stem or "Пациент")
    return sanitize_folder_component(raw)


def build_patient_folder_info(
    primary_path: str | Path,
    *,
    settings: Mapping[str, Any] | None = None,
) -> PrimaryPatientFolderInfo:
    """Read only the fields needed to name the patient workspace.

    Parsing is intentionally reused, not reimplemented: the existing
    ``MedicalTextParser`` remains the source of truth.  Any parsing failure is
    non-fatal for intake and falls back to the source filename.
    """
    path = Path(primary_path)
    fio = ""
    admission_date = ""
    try:
        data = MedicalTextParser().parse_docx(path)
        fio = str(getattr(data, "fio", "") or "").strip()
        admission_date = str(getattr(data, "admission_date", "") or "").strip()
    except Exception:
        pass

    folder_name = build_patient_folder_name(
        fio=fio,
        admission_date=admission_date,
        fallback_stem=path.stem,
        settings=settings,
    )
    return PrimaryPatientFolderInfo(
        fio=fio,
        admission_date=admission_date,
        folder_name=folder_name,
    )
