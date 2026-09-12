"""Safe desktop intake for primary medical documents.

The intake folder is an outer workflow convenience.  It never creates or edits
medical output documents; it only validates a dropped Word file, places it into
an episode subfolder, and returns the moved primary path to the existing app.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Iterable

from desktop_patient_folder import build_patient_folder_info, sanitize_folder_component
from medical_docx_reader import extract_docx_text


DESKTOP_INTAKE_FOLDER_NAME = "Выписанные пациенты"
PRIMARY_FILE_QUIET_SECONDS = 1.5
SUPPORTED_PRIMARY_EXTENSIONS = {".docx", ".docm"}

_STRONG_PRIMARY_MARKERS = (
    "первичный осмотр",
    "первичный прием",
    "направление на госпитализацию",
)
_EXCLUDED_DOCUMENT_MARKERS = (
    "выписной эпикриз",
    "переводной эпикриз",
    "посмертный эпикриз",
    "этапный эпикриз",
    "дневник наблюдения",
    "дневник врача",
    "протокол операции",
    "информированное добровольное согласие",
    "отказ от медицинского вмешательства",
)


def _normalized_text(value: str) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())


def primary_document_score(text: str) -> int:
    """Return a conservative primary/referral score for already extracted text."""
    normalized = _normalized_text(text)
    if not normalized:
        return 0
    if any(marker in normalized for marker in _EXCLUDED_DOCUMENT_MARKERS):
        return -100

    score = 0
    if any(marker in normalized for marker in _STRONG_PRIMARY_MARKERS):
        score += 7
    if "история болезни" in normalized or "иб №" in normalized or "иб n" in normalized:
        score += 2
    if "ф.и.о" in normalized or "фио" in normalized or "фамилия имя отчество" in normalized:
        score += 1
    if "дата поступления" in normalized or "госпитализац" in normalized:
        score += 1
    if "жалоб" in normalized:
        score += 1
    if "диагноз" in normalized:
        score += 1
    if "лечение" in normalized or "план лечения" in normalized:
        score += 1
    if "психический статус" in normalized:
        score += 1
    return score


def is_candidate_word_file(path: str | Path) -> bool:
    p = Path(path)
    name = p.name
    if name.startswith("~$") or name.startswith("."):
        return False
    return p.suffix.lower() in SUPPORTED_PRIMARY_EXTENSIONS


def is_primary_document(path: str | Path) -> bool:
    p = Path(path)
    if not p.is_file() or not is_candidate_word_file(p):
        return False
    try:
        return primary_document_score(extract_docx_text(p)) >= 5
    except Exception:
        return False


def file_is_quiet(path: str | Path, *, quiet_seconds: float = PRIMARY_FILE_QUIET_SECONDS) -> bool:
    """Avoid opening a Word file while Explorer/Word is still copying it."""
    p = Path(path)
    try:
        before = p.stat()
    except OSError:
        return False
    if time.time() - before.st_mtime < max(0.0, quiet_seconds):
        return False
    try:
        with p.open("rb") as stream:
            stream.read(1)
        after = p.stat()
    except OSError:
        return False
    return before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns


def iter_candidate_files(intake_root: str | Path) -> Iterable[Path]:
    """Yield only top-level Word files; patient subfolders are never rescanned."""
    root = Path(intake_root)
    if not root.is_dir():
        return ()
    candidates = [p for p in root.iterdir() if p.is_file() and is_candidate_word_file(p)]
    candidates.sort(key=lambda p: (p.stat().st_mtime_ns if p.exists() else 0, p.name.lower()))
    return tuple(candidates)


def scan_primary_candidates(intake_root: str | Path) -> list[Path]:
    result: list[Path] = []
    for path in iter_candidate_files(intake_root):
        if not file_is_quiet(path):
            continue
        if is_primary_document(path):
            result.append(path)
    return result


def _registry_desktop() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            raw, _ = winreg.QueryValueEx(key, "Desktop")
        expanded = os.path.expandvars(str(raw or "").strip())
        return Path(expanded).expanduser() if expanded else None
    except Exception:
        return None


def discover_desktop() -> Path:
    """Resolve the real Windows desktop, including OneDrive redirected profiles."""
    candidates: list[Path] = []
    registry = _registry_desktop()
    if registry is not None:
        candidates.append(registry)

    for env_name in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
        root = os.environ.get(env_name, "").strip()
        if root:
            candidates.extend((Path(root) / "Desktop", Path(root) / "Рабочий стол"))

    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        candidates.extend((Path(user_profile) / "Desktop", Path(user_profile) / "Рабочий стол"))
    candidates.extend((Path.home() / "Desktop", Path.home() / "Рабочий стол"))

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_dir():
            return candidate

    # On a normal Windows account Desktop exists.  For a newly provisioned
    # profile use the conventional path and let ensure_intake_root create it.
    return Path.home() / "Desktop"


def intake_root_path() -> Path:
    return discover_desktop() / DESKTOP_INTAKE_FOLDER_NAME


def ensure_intake_root() -> Path:
    root = intake_root_path()
    root.mkdir(parents=True, exist_ok=True)
    return root


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_file_content(path: Path, digest: str) -> bool:
    try:
        return path.is_file() and sha256_file(path) == digest
    except OSError:
        return False


def _folder_contains_digest(folder: Path, digest: str) -> Path | None:
    if not folder.is_dir():
        return None
    for child in folder.iterdir():
        if child.is_file() and is_candidate_word_file(child) and _same_file_content(child, digest):
            return child
    return None


def _patient_folder_candidates(root: Path, base_name: str) -> Iterable[Path]:
    yield root / base_name
    for index in range(2, 1000):
        yield root / f"{base_name} ({index})"


def _allocate_patient_folder(root: Path, base_name: str, source_digest: str) -> tuple[Path, Path | None]:
    """Reuse only a folder proven to contain the same primary; otherwise suffix."""
    for folder in _patient_folder_candidates(root, base_name):
        if not folder.exists():
            folder.mkdir(parents=False, exist_ok=False)
            return folder, None
        existing = _folder_contains_digest(folder, source_digest)
        if existing is not None:
            return folder, existing
    raise RuntimeError("Не удалось подобрать свободную подпапку пациента")


def _available_destination(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for index in range(2, 1000):
        candidate = folder / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Не удалось подобрать свободное имя для первичного документа")


def prepare_patient_work_folder(
    source_path: str | Path,
    *,
    intake_root: str | Path | None = None,
    folder_name: str | None = None,
) -> Path:
    """Move a top-level primary into its safe patient subfolder and return it."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not is_candidate_word_file(source):
        raise ValueError(f"Неподдерживаемый первичный документ: {source.name}")

    root = Path(intake_root) if intake_root is not None else ensure_intake_root()
    root.mkdir(parents=True, exist_ok=True)
    info = build_patient_folder_info(source)
    base_name = sanitize_folder_component(folder_name or info.folder_name)
    source_digest = sha256_file(source)
    patient_folder, existing_primary = _allocate_patient_folder(root, base_name, source_digest)

    if existing_primary is not None:
        # A duplicate was dropped into the intake root.  Keep the already placed
        # canonical primary and remove only the proven byte-identical duplicate.
        try:
            if source.resolve() != existing_primary.resolve():
                source.unlink()
        except OSError:
            pass
        return existing_primary

    destination = _available_destination(patient_folder, source.name)
    try:
        os.replace(source, destination)
    except OSError:
        try:
            shutil.move(str(source), str(destination))
        except OSError:
            shutil.copy2(source, destination)
            source.unlink()
    return destination
