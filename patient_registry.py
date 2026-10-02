from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import os
import re
import subprocess
import threading

from medical_formatting import parse_date
from medical_models import normalize_yes_no, parse_sick_leave_value


PATIENT_SUMMARY_ARGUMENT = "--patient-summary"
PATIENT_SUMMARY_TRAY_ARGUMENT = "--patient-summary-tray"
PATIENT_SUMMARY_RUN_VALUE_NAME = "MedicalDiaryAutofill Patients"
PATIENT_SUMMARY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SUPPORTED_WORD_SUFFIXES = {".doc", ".docx", ".docm"}
_PRIMARY_NAME_RE = re.compile(r"(?iu)(?:^|[\s._()\-])(?:первичный|первичка)(?:$|[\s._()\-])")
_DISCHARGE_NAME_RE = re.compile(r"(?iu)(?:^|[\s._()\-])выписной(?:$|[\s._()\-])")
_PRIMARY_PARSE_CACHE_MAX = 512
_PRIMARY_PARSE_CACHE: dict[str, tuple[tuple[int, int, int], object]] = {}
_PRIMARY_PARSE_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class PatientRegistryEntry:
    fio: str
    folder: Path
    primary_path: Path | None
    admission_date: date | None
    sick_leave_needed: bool
    sick_leave_from: date | None
    rvk_referral: bool = False
    rvk_commissariat: str = ""
    warning: str = ""

    def is_present_on(self, value: date) -> bool:
        # The selected root is the current ward census. If the date cannot be
        # recovered from a real Word source, keep the patient visible with a
        # warning instead of silently dropping the whole folder.
        return self.admission_date is None or self.admission_date <= value

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

    @property
    def rvk_patients(self) -> tuple[PatientRegistryEntry, ...]:
        return tuple(item for item in self.patients if item.rvk_referral)


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


def patient_source_candidates(folder: str | Path) -> list[Path]:
    """Prefer explicit primary filenames, then fall back to other Word sources.

    A patient folder is the census source of truth. Doctors may rename a primary
    file or keep only another parseable medical document, so a strict filename
    requirement must not make the whole patient disappear from «Мои пациенты».
    """
    root = Path(folder)
    preferred = primary_candidates(root)
    if preferred:
        return preferred
    if not root.is_dir():
        return []
    rank = {".docx": 0, ".docm": 1, ".doc": 2}
    fallback = [
        path
        for path in root.iterdir()
        if (
            path.is_file()
            and not path.name.startswith("~$")
            and path.suffix.lower() in SUPPORTED_WORD_SUFFIXES
            and not is_discharge_patient_filename(path)
        )
    ]
    return sorted(fallback, key=lambda p: (rank.get(p.suffix.lower(), 9), p.name.casefold()))


def is_discharge_patient_filename(path: str | Path) -> bool:
    candidate = Path(path)
    if candidate.suffix.lower() not in SUPPORTED_WORD_SUFFIXES:
        return False
    stem = _normalize_primary_stem(candidate.stem)
    return bool(_DISCHARGE_NAME_RE.search(stem))


def has_discharge_patient_document(folder: str | Path) -> bool:
    """Return True only for a discharge file that belongs to this patient folder.

    The user contract is «<Фамилия пациента> Выписной». A generic template,
    copied example or another person's discharge must not hide the current
    patient merely because its filename contains the word «Выписной».
    """
    root = Path(folder)
    if not root.is_dir():
        return False

    folder_key = _normalize_primary_stem(root.name).casefold()
    folder_tokens = [part for part in re.split(r"[\s._()\-]+", folder_key) if part]
    surname = folder_tokens[0] if folder_tokens else ""
    if not surname:
        return False

    for path in root.iterdir():
        if not path.is_file() or not is_discharge_patient_filename(path):
            continue
        stem_key = _normalize_primary_stem(path.stem).casefold()
        stem_tokens = [part for part in re.split(r"[\s._()\-]+", stem_key) if part]
        first_token = stem_tokens[0] if stem_tokens else ""
        if first_token == surname:
            return True
    return False


def _date_value(value: str) -> date | None:
    parsed = parse_date(str(value or "").strip())
    return parsed.date() if parsed else None


def _admission_date_from_primary_first_line(path: Path) -> date | None:
    """Registry-specific fallback for real primary files.

    In the ward folder contract the primary/первичка file itself identifies the
    document kind, and doctors commonly put the admission date as the first
    non-empty Word line without repeating «Первичный осмотр» on that line.
    The generic medical parser is intentionally stricter to avoid confusing a
    birth date with admission in arbitrary documents. Here it is safe to accept
    only a date at the *start of the first non-empty line* of an already
    filename-validated primary document.
    """
    try:
        from medical_docx_reader import extract_docx_text

        text = extract_docx_text(path)
    except Exception:
        return None

    first_line = next((line.strip() for line in str(text or "").splitlines() if line.strip()), "")
    if not first_line:
        return None
    lowered = first_line.lower().replace("ё", "е")
    if any(marker in lowered for marker in ("дата рождения", "год рождения", "г.р", "возраст")):
        return None
    match = re.match(
        r"^\s*(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}|\d{6,8})(?=$|\s|[,;])",
        first_line,
    )
    if not match:
        return None
    return _date_value(re.sub(r"\s+", "", match.group(1)))


def _sick_leave_state_from_primary_text(path: Path) -> tuple[str, str]:
    """Recover the LN decision/date directly from a real primary Word source.

    Word tables can split a label and its value into adjacent cells. The generic
    inline parser intentionally processes each extracted line independently, so
    «Больничный лист» in one cell and «с 25.09.2026» in the next cell may not
    become one PatientData field. For the patient registry we have a narrower
    contract and can safely inspect the full primary text around an explicit LN
    label.
    """
    try:
        from medical_docx_reader import extract_docx_text

        text = " ".join(str(extract_docx_text(path) or "").split())
    except Exception:
        return "", ""
    if not text:
        return "", ""

    label = r"(?:больничн(?:ый|ого)\s+лист|лист\s+нетрудоспособности|лн)"
    prefix = rf"(?:нужен\s+ли\s+|нужен\s+)?{label}"
    if re.search(
        rf"(?i)\b{prefix}\b\s*[:;,.—–-]?\s*(?:нет\b|не\s+нуж(?:ен|на|но)\b|не\s+требуется\b)",
        text,
    ):
        return "нет", ""

    date_token = r"(\d{6,8}|\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})"
    positive = re.search(
        rf"(?i)\b{prefix}\b\s*[:;,.—–-]?\s*(?:да\b\s*[,;:-]?\s*)?(?:с|от)\s+{date_token}",
        text,
    )
    if positive:
        return "да", re.sub(r"\s+", "", positive.group(1))

    if re.search(rf"(?i)\b{prefix}\b\s*[:;,.—–-]?\s*да\b", text):
        return "да", ""
    return "", ""


def _sick_leave_state(data, primary_path: Path | None = None) -> tuple[bool, date | None, str]:
    explicit_decision = normalize_yes_no(getattr(data, "expert_sick_leave_needed", ""))
    explicit_from = str(getattr(data, "expert_sick_leave_from", "") or "").strip()
    rendered_decision, rendered_from = parse_sick_leave_value(
        str(getattr(data, "sick_leave", "") or "")
    )
    decision = explicit_decision or rendered_decision
    raw_from = explicit_from or rendered_from

    # Do not override an explicit negative decision. Otherwise recover a missing
    # decision/date from the actual primary Word text, including split table cells.
    if decision != "нет" and primary_path is not None and (not decision or not raw_from):
        fallback_decision, fallback_from = _sick_leave_state_from_primary_text(primary_path)
        if not decision:
            decision = fallback_decision
        if decision == "да" and not raw_from and fallback_decision == "да":
            raw_from = fallback_from

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



_RVK_DISTRICT_CANONICAL = {
    "автозаводский": "Автозаводский",
    "автозаводского": "Автозаводский",
    "ленинский": "Ленинский",
    "ленинского": "Ленинский",
    "канавинский": "Канавинский",
    "канавинского": "Канавинский",
    "канвинский": "Канавинский",
    "канвинского": "Канавинский",
    "сормовский": "Сормовский",
    "сормовского": "Сормовский",
    "московский": "Московский",
    "московского": "Московский",
    "советский": "Советский",
    "советского": "Советский",
    "нижегородский": "Нижегородский",
    "нижегородского": "Нижегородский",
    "приокский": "Приокский",
    "приокского": "Приокский",
}


def _normalize_rvk_commissariat_text(value: str) -> str:
    """Normalize an RVK district/commissariat phrase for the existing Act popup."""
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    text = text.strip(" \t,.;:—–-()[]")
    text = re.sub(r"(?iu)^\s*да\s*/\s*нет\s*[:;,.—–-]?\s*", "", text)
    text = re.sub(r"(?iu)^\s*(?:да|есть|имеется)\b\s*[:;,.—–-]?\s*", "", text)
    text = re.sub(r"(?iu)^\s*(?:от|из)\s+", "", text)
    text = re.sub(
        r"(?iu)^\s*(?:рвк|военн(?:ого|ый)\s+комиссариат(?:а)?|военкомат(?:а)?)\s*[:;,.—–-]?\s*",
        "",
        text,
    )
    text = text.strip(" \t,.;:—–-()[]")
    text = re.sub(r"(?iu)\s+военкомат(?:а|у|е|ом)?\s*$", "", text).strip(" \t,.;:—–-()[]")
    text = re.sub(r"(?iu)\s+район(?:а|ов|у|е|ом)?\s*$", "", text).strip(" \t,.;:—–-()[]")
    if not text:
        return ""

    lowered = text.lower().replace("ё", "е")
    if lowered in {"да", "нет", "да нет"}:
        return ""
    if re.search(
        r"(?iu)\b(?:диагноз|жалоб|анамнез|больничн|должност|место\s+работы|"
        r"ф\.?\s*и\.?\s*о\.?|год\s+рождения|дата\s+рождения|психическ\w+\s+статус)\b",
        text,
    ):
        return ""

    combined = {
        "сормовский и московский": "Сормовский и Московский",
        "сормовского и московского": "Сормовский и Московский",
        "московский и сормовский": "Сормовский и Московский",
        "московского и сормовского": "Сормовский и Московский",
    }
    if lowered in combined:
        return combined[lowered]
    if lowered in _RVK_DISTRICT_CANONICAL:
        return _RVK_DISTRICT_CANONICAL[lowered]

    parts = [
        part.strip()
        for part in re.split(r"(?iu)\s*(?:,|/|\\\\|\s+и\s+)\s*", text)
        if part.strip()
    ]
    if len(parts) > 1:
        canonical_parts = []
        for part in parts:
            normalized_part = _RVK_DISTRICT_CANONICAL.get(part.lower().replace("ё", "е"))
            if not normalized_part:
                canonical_parts = []
                break
            canonical_parts.append(normalized_part)
        if canonical_parts:
            return " и ".join(dict.fromkeys(canonical_parts))

    return text


def _rvk_referral_state_from_text(text: str) -> tuple[str, str]:
    """Recover RVK yes/no and district from common primary-exam formulations."""
    lines = [" ".join(line.split()) for line in str(text or "").splitlines() if line.strip()]
    positive_without_area = False
    context_re = re.compile(
        r"(?iu)(?:"
        r"направлен\w*.*(?:\bрвк\b|военком|военн\w*\s+комиссариат)|"
        r"госпитализ\w*.*(?:\bрвк\b|военком|военн\w*\s+комиссариат)|"
        r"(?:\bрвк\b|военком|военн\w*\s+комиссариат).*направлен\w*"
        r")"
    )
    prefix_patterns = (
        r"(?iu)^.*?направлен\w*\s+(?:(?:от|из)\s+)?(?:рвк|военн(?:ого|ый)\s+комиссариат(?:а)?|военкомат(?:а)?)\s*",
        r"(?iu)^.*?госпитализ\w*\s+(?:по\s+направлени\w*\s+)?(?:(?:от|из)\s+)?(?:рвк|военн(?:ого|ый)\s+комиссариат(?:а)?|военкомат(?:а)?)\s*",
        r"(?iu)^.*?по\s+направлени\w*\s+из\s+",
    )

    for index, line in enumerate(lines):
        if not context_re.search(line):
            continue

        decision_text = re.sub(r"(?iu)\bда\s*/\s*нет\b", "", line)
        if (
            re.search(r"(?iu)\bбез\s+направлени\w*(?:\s+из|\s+от)?\s*(?:рвк|военком|военн\w*\s+комиссариат)", decision_text)
            or re.search(r"(?iu)\bне\s+(?:направлен\w*|госпитализ\w*)\b", decision_text)
            or re.search(r"(?iu)(?:\bрвк\b|военком|военн\w*\s+комиссариат).*?[:;,.—–-]?\s*\bнет\b", decision_text)
        ):
            return "нет", ""

        tail = line
        for pattern in prefix_patterns:
            replaced = re.sub(pattern, "", tail)
            if replaced != tail:
                tail = replaced
                break
        area = _normalize_rvk_commissariat_text(tail)
        if area:
            return "да", area

        # DOCX tables may place the label and district into adjacent cells/lines.
        if index + 1 < len(lines):
            next_area = _normalize_rvk_commissariat_text(lines[index + 1])
            if next_area and not context_re.search(lines[index + 1]):
                return "да", next_area
        positive_without_area = True

    return ("да", "") if positive_without_area else ("", "")


def _rvk_referral_state(data, primary_path: Path | None = None) -> tuple[bool, str, str]:
    explicit_decision = normalize_yes_no(getattr(data, "rvk_referral_present", ""))
    explicit_area = _normalize_rvk_commissariat_text(
        str(getattr(data, "rvk_referral_commissariat", "") or "")
    )
    raw_value = str(getattr(data, "rvk_referral", "") or "").strip()

    decision = explicit_decision
    area = explicit_area
    if decision != "нет" and raw_value and (not decision or not area):
        raw_decision, raw_area = _rvk_referral_state_from_text(raw_value)
        if not raw_decision:
            compact = re.sub(r"(?iu)^\s*да\s*/\s*нет\s*[:;,.—–-]?\s*", "", raw_value).strip()
            exact = normalize_yes_no(compact)
            if exact:
                raw_decision = exact
            elif re.match(r"(?iu)^\s*да\b", compact):
                raw_decision = "да"
                raw_area = _normalize_rvk_commissariat_text(
                    re.sub(r"(?iu)^\s*да\b\s*[:;,.—–-]?\s*", "", compact)
                )
            else:
                raw_area = _normalize_rvk_commissariat_text(compact)
                if raw_area:
                    raw_decision = "да"
        if not decision:
            decision = raw_decision
        if decision == "да" and not area and raw_decision == "да":
            area = raw_area

    if decision != "нет" and primary_path is not None and (not decision or not area):
        try:
            from medical_docx_reader import extract_docx_text

            fallback_decision, fallback_area = _rvk_referral_state_from_text(
                str(extract_docx_text(primary_path) or "")
            )
        except Exception:
            fallback_decision, fallback_area = "", ""
        if not decision:
            decision = fallback_decision
        if decision == "да" and not area and fallback_decision == "да":
            area = fallback_area

    if decision == "нет":
        return False, "", ""
    if decision == "да":
        if not area:
            return True, "", "РВК отмечен, но район не распознан."
        return True, area, ""
    return False, "", ""


def _primary_file_signature(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return (
        int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
        int(getattr(stat, "st_ctime_ns", int(stat.st_ctime * 1_000_000_000))),
        int(stat.st_size),
    )


def _default_parser(path: Path):
    """Parse each unchanged primary only once per process.

    «Мои пациенты» may contain dozens of Word files. Re-opening the window used
    to rebuild the full parser/service graph for every patient every time. A
    cheap filesystem signature keeps the second and subsequent scans fast while
    invalidating immediately when Word changes the file.
    """
    from medical_service import MedicalDocumentService

    candidate = Path(path)
    try:
        key = os.path.normcase(str(candidate.resolve()))
        signature = _primary_file_signature(candidate)
    except OSError:
        return MedicalDocumentService().parse_primary_document(candidate)

    with _PRIMARY_PARSE_CACHE_LOCK:
        cached = _PRIMARY_PARSE_CACHE.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]

    data = MedicalDocumentService().parse_primary_document(candidate)
    with _PRIMARY_PARSE_CACHE_LOCK:
        _PRIMARY_PARSE_CACHE[key] = (signature, data)
        if len(_PRIMARY_PARSE_CACHE) > _PRIMARY_PARSE_CACHE_MAX:
            overflow = len(_PRIMARY_PARSE_CACHE) - _PRIMARY_PARSE_CACHE_MAX
            for old_key in list(_PRIMARY_PARSE_CACHE)[:overflow]:
                if old_key != key:
                    _PRIMARY_PARSE_CACHE.pop(old_key, None)
    return data


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
        # The selected root represents the current ward census. A stray folder
        # that already contains a Word document named "... Выписной" is treated
        # as discharged and must not be counted in the current patient summary.
        if has_discharge_patient_document(patient_folder):
            continue

        candidates = patient_source_candidates(patient_folder)
        if not candidates:
            warning = "В папке пациента не найден Word-документ для распознавания."
            issues.append(PatientRegistryIssue(patient_folder, warning))
            patients.append(
                PatientRegistryEntry(
                    fio=patient_folder.name,
                    folder=patient_folder,
                    primary_path=None,
                    admission_date=None,
                    sick_leave_needed=False,
                    sick_leave_from=None,
                    warning=warning,
                )
            )
            continue

        parsed_data = None
        chosen = candidates[0]
        last_error = None
        for candidate in candidates:
            try:
                parsed_data = parse(candidate)
                chosen = candidate
                break
            except Exception as exc:
                last_error = exc

        warnings: list[str] = []
        if parsed_data is None:
            # Keep the folder in the census. Registry-specific fallbacks can
            # still recover admission/LN facts directly from the Word source,
            # while FIO safely falls back to the folder name.
            warnings.append(
                f"Первичный документ не разобран общим парсером ({type(last_error).__name__ if last_error else 'ошибка'})."
            )
            issues.append(
                PatientRegistryIssue(
                    patient_folder,
                    warnings[-1],
                )
            )

        admission = _date_value(getattr(parsed_data, "admission_date", ""))
        if admission is None:
            admission = _admission_date_from_primary_first_line(chosen)
        if admission is None:
            warnings.append("Дата поступления не распознана.")
            issues.append(
                PatientRegistryIssue(
                    patient_folder,
                    "Не распознана дата поступления ни общим парсером, ни в первой строке первичного документа.",
                )
            )
        elif admission > target_date:
            continue

        fio = " ".join(str(getattr(parsed_data, "fio", "") or "").split()) or patient_folder.name
        sick_needed, sick_from, sick_warning = _sick_leave_state(parsed_data, chosen)
        if sick_warning:
            warnings.append(sick_warning)
        rvk_referral, rvk_commissariat, rvk_warning = _rvk_referral_state(parsed_data, chosen)
        if rvk_warning:
            warnings.append(rvk_warning)
        warning = " ".join(dict.fromkeys(warnings))
        patients.append(
            PatientRegistryEntry(
                fio=fio,
                folder=patient_folder,
                primary_path=chosen,
                admission_date=admission,
                sick_leave_needed=sick_needed,
                sick_leave_from=sick_from,
                rvk_referral=rvk_referral,
                rvk_commissariat=rvk_commissariat,
                warning=warning,
            )
        )

    # The operational view must put patients with an active/declared sick
    # leave first. Within each group keep a stable alphabetical order.
    patients.sort(
        key=lambda item: (
            0 if item.is_on_sick_leave_on(target_date) else 1,
            item.fio.casefold(),
            item.admission_date or date.max,
            item.primary_path.name.casefold() if item.primary_path is not None else "",
        )
    )
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
    """Return the latest Wednesday within sick-leave days 7..15 inclusive.

    The sick-leave opening date is day one. A commission must therefore never
    be scheduled before inclusive day 7 and never after inclusive day 15.
    Because the clinical workflow fixes commissions to Wednesdays, choose the
    latest Wednesday inside that safe window. The window is nine days wide, so
    it always contains at least one Wednesday.
    """
    earliest = sick_leave_from + timedelta(days=6)
    latest = sick_leave_from + timedelta(days=14)
    days_back = (latest.weekday() - 2) % 7
    candidate = latest - timedelta(days=days_back)
    if candidate < earliest:
        candidate += timedelta(days=7)
    if not (earliest <= candidate <= latest):
        raise AssertionError("VK Wednesday must stay inside inclusive sick-leave days 7..15")
    return candidate


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


def hospitalization_days_on(entry: PatientRegistryEntry, value: date) -> int | None:
    if entry.admission_date is None:
        return None
    return inclusive_days(entry.admission_date, value)


def open_patient_folder(path: str | Path) -> bool:
    """Open a patient's directory in the platform file manager."""
    folder = Path(path).expanduser()
    if not folder.exists() or not folder.is_dir():
        return False
    try:
        if os.name == "nt":
            startfile = getattr(os, "startfile")
            startfile(str(folder))
        else:
            import sys

            command = ["open", str(folder)] if sys.platform == "darwin" else ["xdg-open", str(folder)]
            subprocess.Popen(command)
        return True
    except (AttributeError, OSError, subprocess.SubprocessError):
        return False


class PatientSummaryTray:
    """Small native Windows notification-area controller for the patient summary.

    Tk owns all actual windows and must stay on its main thread. The Win32 tray
    icon therefore runs a tiny message loop on a daemon thread and communicates
    only through thread-safe Events. The Tk window polls those Events and decides
    whether to restore or close itself.
    """

    _TRAY_MESSAGE = 0x0400 + 73  # WM_USER + private app offset
    _CMD_OPEN = 1001
    _CMD_CLOSE = 1002

    def __init__(self, title: str = "Мои пациенты") -> None:
        self.title = str(title or "Мои пациенты")[:127]
        self._restore_requested = threading.Event()
        self._close_requested = threading.Event()
        self._ready = threading.Event()
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._started_ok = False

    def start(self) -> bool:
        if os.name != "nt":
            return False
        if self._thread is not None and self._thread.is_alive():
            return self._started_ok
        self._restore_requested.clear()
        self._close_requested.clear()
        self._ready.clear()
        self._stop_requested.clear()
        self._started_ok = False
        self._thread = threading.Thread(
            target=self._run_windows_tray,
            name="MedicalDiaryAutofillPatientTray",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._started_ok

    def stop(self) -> None:
        self._stop_requested.set()
        hwnd = self._hwnd
        if hwnd:
            try:
                import win32con
                import win32gui

                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None
        self._hwnd = None

    def consume_restore_request(self) -> bool:
        requested = self._restore_requested.is_set()
        if requested:
            self._restore_requested.clear()
        return requested

    def consume_close_request(self) -> bool:
        requested = self._close_requested.is_set()
        if requested:
            self._close_requested.clear()
        return requested

    def _run_windows_tray(self) -> None:
        try:
            import win32api
            import win32con
            import win32gui

            class_name = f"MedicalDiaryAutofillPatientTray_{os.getpid()}_{id(self)}"
            hinstance = win32api.GetModuleHandle(None)
            if self._stop_requested.is_set():
                self._ready.set()
                return

            def window_proc(hwnd, msg, wparam, lparam):
                if msg == self._TRAY_MESSAGE:
                    if lparam in (win32con.WM_LBUTTONUP, win32con.WM_LBUTTONDBLCLK):
                        self._restore_requested.set()
                        return 0
                    if lparam == win32con.WM_RBUTTONUP:
                        menu = win32gui.CreatePopupMenu()
                        try:
                            win32gui.AppendMenu(menu, win32con.MF_STRING, self._CMD_OPEN, "Открыть сводку")
                            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
                            win32gui.AppendMenu(menu, win32con.MF_STRING, self._CMD_CLOSE, "Закрыть сводку")
                            x, y = win32gui.GetCursorPos()
                            win32gui.SetForegroundWindow(hwnd)
                            command = win32gui.TrackPopupMenu(
                                menu,
                                win32con.TPM_LEFTALIGN | win32con.TPM_RETURNCMD | win32con.TPM_NONOTIFY,
                                x,
                                y,
                                0,
                                hwnd,
                                None,
                            )
                            if command == self._CMD_OPEN:
                                self._restore_requested.set()
                            elif command == self._CMD_CLOSE:
                                self._close_requested.set()
                        finally:
                            win32gui.DestroyMenu(menu)
                        return 0
                if msg == win32con.WM_CLOSE:
                    win32gui.DestroyWindow(hwnd)
                    return 0
                if msg == win32con.WM_DESTROY:
                    win32gui.PostQuitMessage(0)
                    return 0
                return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

            wnd_class = win32gui.WNDCLASS()
            wnd_class.hInstance = hinstance
            wnd_class.lpszClassName = class_name
            wnd_class.lpfnWndProc = window_proc
            win32gui.RegisterClass(wnd_class)
            hwnd = win32gui.CreateWindow(
                class_name,
                class_name,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                hinstance,
                None,
            )
            self._hwnd = hwnd
            if self._stop_requested.is_set():
                win32gui.DestroyWindow(hwnd)
                self._ready.set()
                return
            icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
            notify_data = (
                hwnd,
                0,
                win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
                self._TRAY_MESSAGE,
                icon,
                self.title,
            )
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, notify_data)
            self._started_ok = True
            self._ready.set()
            try:
                win32gui.PumpMessages()
            finally:
                try:
                    win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 0))
                except Exception:
                    pass
                try:
                    win32gui.UnregisterClass(class_name, hinstance)
                except Exception:
                    pass
        except Exception:
            self._started_ok = False
            self._ready.set()
        finally:
            self._hwnd = None


def launch_patient_summary_tray_process() -> bool:
    """Launch an independent patient-summary host that survives the main GUI.

    A summary opened from the main application is otherwise only a Tk child of
    that process, so closing the main application necessarily removes its tray
    icon. The detached host owns the summary/tray lifecycle independently.
    """
    if os.name != "nt":
        return False
    try:
        from startup import _desktop_runtime_command

        command = _desktop_runtime_command(PATIENT_SUMMARY_TRAY_ARGUMENT)
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        subprocess.Popen(
            command,
            close_fds=True,
            creationflags=creationflags,
        )
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


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

def remove_patient_summary_autostart() -> None:
    """Remove the per-user logon summary registration during uninstall."""
    if os.name != "nt":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            PATIENT_SUMMARY_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(key, PATIENT_SUMMARY_RUN_VALUE_NAME)
            except FileNotFoundError:
                pass
    except (OSError, ImportError):
        pass
