from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import os
import re
import subprocess

from medical_formatting import parse_date
from medical_models import normalize_yes_no, parse_sick_leave_value


PATIENT_SUMMARY_ARGUMENT = "--patient-summary"
PATIENT_SUMMARY_RUN_VALUE_NAME = "MedicalDiaryAutofill Patients"
PATIENT_SUMMARY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SUPPORTED_WORD_SUFFIXES = {".doc", ".docx", ".docm"}
_PRIMARY_NAME_RE = re.compile(r"(?iu)(?:^|[\s._()\-])(?:первичный|первичка)(?:$|[\s._()\-])")


@dataclass(frozen=True)
class PatientRegistryEntry:
    fio: str
    folder: Path
    primary_path: Path
    admission_date: date
    sick_leave_needed: bool
    sick_leave_from: date | None
    warning: str = ""

    def is_present_on(self, value: date) -> bool:
        return self.admission_date <= value

    def is_on_sick_leave_on(self, value: date) -> bool:
        if not self.sick_leave_needed:
            return False
        return self.sick_leave_from is None or self.sick_leave_from <= value


@dataclass(frozen=True)
class PatientRegistryIssue:
    folder: Path
    message: str


@dataclass(frozen=True)
class PatientRegistrySnapshot:
    root: Path
    as_of: date
    patients: tuple[PatientRegistryEntry, ...]
    issues: tuple[PatientRegistryIssue, ...]

    @property
    def sick_leave_patients(self) -> tuple[PatientRegistryEntry, ...]:
        return tuple(item for item in self.patients if item.is_on_sick_leave_on(self.as_of))


def _normalize_primary_stem(value: str) -> str:
    return " ".join(str(value or "").replace("ё", "е").split())


def is_primary_patient_filename(path: str | Path) -> bool:
    candidate = Path(path)
    if candidate.suffix.lower() not in SUPPORTED_WORD_SUFFIXES:
        return False
    stem = _normalize_primary_stem(candidate.stem)
    return bool(_PRIMARY_NAME_RE.search(stem))


def primary_candidates(folder: str | Path) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        return []
    rank = {".docx": 0, ".docm": 1, ".doc": 2}
    result = [
        path
        for path in root.iterdir()
        if path.is_file() and is_primary_patient_filename(path)
    ]
    return sorted(result, key=lambda p: (rank.get(p.suffix.lower(), 9), p.name.casefold()))


def _date_value(value: str) -> date | None:
    parsed = parse_date(str(value or "").strip())
    return parsed.date() if parsed else None


def _sick_leave_state(data) -> tuple[bool, date | None, str]:
    explicit_decision = normalize_yes_no(getattr(data, "expert_sick_leave_needed", ""))
    explicit_from = str(getattr(data, "expert_sick_leave_from", "") or "").strip()
    rendered_decision, rendered_from = parse_sick_leave_value(
        str(getattr(data, "sick_leave", "") or "")
    )
    decision = explicit_decision or rendered_decision
    raw_from = explicit_from or rendered_from
    parsed_from = _date_value(raw_from) if raw_from else None

    if decision == "нет":
        return False, None, ""
    if decision == "да":
        if raw_from and parsed_from is None:
            return True, None, "Дата начала больничного указана, но не распознана."
        if not raw_from:
            return True, None, "Больничный отмечен как нужный, но дата начала не указана."
        return True, parsed_from, ""
    return False, None, ""


def _default_parser(path: Path):
    from medical_service import MedicalDocumentService

    return MedicalDocumentService().parse_primary_document(path)


def scan_patient_registry(
    root: str | Path,
    *,
    as_of: date | None = None,
    parser=None,
) -> PatientRegistrySnapshot:
    directory = Path(root).expanduser()
    if not directory.exists() or not directory.is_dir():
        raise ValueError("Папка пациентов не существует или недоступна.")

    target_date = as_of or date.today()
    parse = parser or _default_parser
    patients: list[PatientRegistryEntry] = []
    issues: list[PatientRegistryIssue] = []

    for patient_folder in sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.name.casefold()):
        candidates = primary_candidates(patient_folder)
        if not candidates:
            continue

        parsed_data = None
        chosen = None
        last_error = None
        for candidate in candidates:
            try:
                parsed_data = parse(candidate)
                chosen = candidate
                break
            except Exception as exc:
                last_error = exc

        if parsed_data is None or chosen is None:
            issues.append(
                PatientRegistryIssue(
                    patient_folder,
                    f"Не удалось прочитать первичный документ ({type(last_error).__name__ if last_error else 'ошибка'}).",
                )
            )
            continue

        admission = _date_value(getattr(parsed_data, "admission_date", ""))
        if admission is None:
            issues.append(PatientRegistryIssue(patient_folder, "Не распознана дата поступления."))
            continue
        if admission > target_date:
            continue

        fio = " ".join(str(getattr(parsed_data, "fio", "") or "").split()) or patient_folder.name
        sick_needed, sick_from, warning = _sick_leave_state(parsed_data)
        patients.append(
            PatientRegistryEntry(
                fio=fio,
                folder=patient_folder,
                primary_path=chosen,
                admission_date=admission,
                sick_leave_needed=sick_needed,
                sick_leave_from=sick_from,
                warning=warning,
            )
        )

    patients.sort(key=lambda item: (item.fio.casefold(), item.admission_date, item.primary_path.name.casefold()))
    return PatientRegistrySnapshot(
        root=directory,
        as_of=target_date,
        patients=tuple(patients),
        issues=tuple(issues),
    )


def inclusive_days(start: date, finish: date) -> int:
    if finish < start:
        return 0
    return (finish - start).days + 1


def first_sick_leave_vk_date(sick_leave_from: date) -> date:
    """Return the Wednesday nearest to the 15th inclusive sick-leave day.

    Day one is the sick-leave opening date, so the 15th day is start + 14 days.
    The clinical workflow fixes commissions to Wednesdays; therefore the
    calendar chooses the nearest Wednesday to that 15-day milestone. Future
    commissions repeat every two Wednesdays (14 calendar days).
    """
    milestone = sick_leave_from + timedelta(days=14)
    days_back = (milestone.weekday() - 2) % 7
    previous_wednesday = milestone - timedelta(days=days_back)
    next_wednesday = previous_wednesday + timedelta(days=7)
    if previous_wednesday < sick_leave_from:
        return next_wednesday
    if (milestone - previous_wednesday) <= (next_wednesday - milestone):
        return previous_wednesday
    return next_wednesday

def next_sick_leave_vk_date(sick_leave_from: date, as_of: date) -> date:
    first = first_sick_leave_vk_date(sick_leave_from)
    if as_of <= first:
        return first
    delta = (as_of - first).days
    cycles = (delta + 13) // 14
    return first + timedelta(days=cycles * 14)


def sick_leave_days_on(entry: PatientRegistryEntry, value: date) -> int | None:
    if not entry.sick_leave_needed or entry.sick_leave_from is None:
        return None
    return inclusive_days(entry.sick_leave_from, value)


def hospitalization_days_on(entry: PatientRegistryEntry, value: date) -> int:
    return inclusive_days(entry.admission_date, value)


def install_patient_summary_autostart() -> bool:
    """Register one visible patient-summary launch per Windows sign-in."""
    if os.name != "nt" or os.environ.get("CI", "").strip():
        return False
    try:
        import winreg
        from startup import _desktop_runtime_command

        desired = subprocess.list2cmdline(_desktop_runtime_command(PATIENT_SUMMARY_ARGUMENT))
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            PATIENT_SUMMARY_RUN_KEY,
            0,
            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
        ) as key:
            try:
                current, _kind = winreg.QueryValueEx(key, PATIENT_SUMMARY_RUN_VALUE_NAME)
            except FileNotFoundError:
                current = ""
            if str(current or "") != desired:
                winreg.SetValueEx(
                    key,
                    PATIENT_SUMMARY_RUN_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    desired,
                )
        return True
    except (OSError, ImportError):
        return False
