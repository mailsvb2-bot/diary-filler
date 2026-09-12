from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox
import tkinter as tk
from typing import Any, Iterable, Mapping

from app_config import APP_TITLE


# ---------------------------------------------------------------------------
# Original application startup helpers
# ---------------------------------------------------------------------------


def _startup_log_path() -> Path:
    try:
        return Path(__file__).resolve().parent / "startup_error.log"
    except Exception:
        return Path.cwd() / "startup_error.log"


def _write_startup_error(details: str) -> None:
    try:
        _startup_log_path().write_text(details, encoding="utf-8")
    except Exception:
        pass


def _create_root(*, require_dnd: bool = False):
    """Create the root; production may fall back, release probes require TkDND."""
    try:
        from tkinterdnd2 import TkinterDnD  # type: ignore

        return TkinterDnD.Tk()
    except Exception:
        if require_dnd:
            raise
        return tk.Tk()


# ---------------------------------------------------------------------------
# Optional desktop intake convenience layer
#
# Critical boundary: nothing below generates or edits medical documents.  It
# only detects a dropped primary document, creates/moves it into a patient work
# folder, and hands the resulting path to the application's already-existing
# _apply_primary_document_path(...).  The medical/diary generation engine stays
# untouched.
# ---------------------------------------------------------------------------


DESKTOP_INTAKE_FOLDER_NAME = "Выписанные пациенты"
DESKTOP_INTAKE_AGENT_ARGUMENT = "--intake-agent"
DESKTOP_INTAKE_PRIMARY_ARGUMENT = "--intake-primary"
_DESKTOP_INTAKE_SUPPORTED_EXTENSIONS = {".docx", ".docm"}
_DESKTOP_INTAKE_QUIET_SECONDS = 1.5
_DESKTOP_INTAKE_GUI_POLL_MS = 1600
_DESKTOP_INTAKE_HEARTBEAT_MS = 1800
_DESKTOP_INTAKE_HEARTBEAT_MAX_AGE_SECONDS = 6.0
_DESKTOP_INTAKE_AGENT_POLL_SECONDS = 2.0
_DESKTOP_INTAKE_AGENT_RELAUNCH_COOLDOWN_SECONDS = 30.0
_DESKTOP_INTAKE_AGENT_MUTEX_HANDOFF_SECONDS = 8.0
_DESKTOP_INTAKE_AGENT_MUTEX_NAME = "Local\\MedicalDiaryAutofillDesktopIntakeAgent"
_DESKTOP_INTAKE_MAX_LOG_BYTES = 128 * 1024
_DESKTOP_INTAKE_HANDOFF_SCHEMA = 1

_DESKTOP_INTAKE_STRONG_PRIMARY_MARKERS = (
    "первичный осмотр",
    "первичный прием",
    "направление на госпитализацию",
)
_DESKTOP_INTAKE_EXCLUDED_MARKERS = (
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

DESKTOP_FOLDER_NAMING_OPTIONS = {
    "full_fio": "ФИО полностью",
    "surname_initials": "Фамилия полностью, Имя и Отчество буквами",
    "surname_name": "Фамилия Имя",
    "admission_date": "Дата поступления",
    "discharge_date": "Дата выписки",
    "admission_discharge_dates": "Дата поступления и дата выписки",
    "admission_month": "Месяц поступления",
    "discharge_month": "Месяц выписки",
}
DESKTOP_FOLDER_NAMING_DEFAULT = {
    "parts": ["surname_initials", "admission_month"],
    "date_format": "short",
}
_DESKTOP_RUSSIAN_MONTHS = (
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
_DESKTOP_INVALID_WINDOWS_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DESKTOP_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_DESKTOP_HUMAN_NAME_PART_RE = re.compile(
    r"(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]{2,})(?:-(?:[А-ЯЁ][а-яё]+|[А-ЯЁ]{2,}))?"
)
_DESKTOP_INITIALS_RE = re.compile(r"(?:[А-ЯЁ]\.){1,2}")
_DESKTOP_BAD_FIO_WORDS = {
    "дата",
    "рождения",
    "диагноз",
    "адрес",
    "история",
    "болезни",
    "направление",
}


@dataclass(frozen=True)
class DesktopPatientFolderInfo:
    fio: str
    admission_date: str
    folder_name: str


def _desktop_runtime_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA", "").strip() or os.environ.get("APPDATA", "").strip()
    base = Path(root) if root else Path.home() / ".medical_diary_autofill"
    path = base / "MedicalDiaryAutofill"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _desktop_normalized_text(value: str) -> str:
    return " ".join(str(value or "").lower().replace("ё", "е").split())


def desktop_intake_primary_score(text: str) -> int:
    """Conservatively classify text before the existing parser is invoked."""
    normalized = _desktop_normalized_text(text)
    if not normalized:
        return 0
    if any(marker in normalized for marker in _DESKTOP_INTAKE_EXCLUDED_MARKERS):
        return -100

    score = 0
    if any(marker in normalized for marker in _DESKTOP_INTAKE_STRONG_PRIMARY_MARKERS):
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


def desktop_intake_is_candidate_word_file(path: str | Path) -> bool:
    candidate = Path(path)
    if candidate.name.startswith("~$") or candidate.name.startswith("."):
        return False
    return candidate.suffix.lower() in _DESKTOP_INTAKE_SUPPORTED_EXTENSIONS


def desktop_intake_is_primary_document(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.is_file() or not desktop_intake_is_candidate_word_file(candidate):
        return False
    try:
        from medical_docx_reader import extract_docx_text

        return desktop_intake_primary_score(extract_docx_text(candidate)) >= 5
    except Exception:
        return False


def desktop_intake_file_is_quiet(
    path: str | Path,
    *,
    quiet_seconds: float = _DESKTOP_INTAKE_QUIET_SECONDS,
) -> bool:
    """Do not open a Word file while Explorer/Word is still copying it."""
    candidate = Path(path)
    try:
        before = candidate.stat()
    except OSError:
        return False
    if time.time() - before.st_mtime < max(0.0, quiet_seconds):
        return False
    try:
        with candidate.open("rb") as stream:
            stream.read(1)
        after = candidate.stat()
    except OSError:
        return False
    return before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns


def desktop_intake_iter_candidates(intake_root: str | Path) -> tuple[Path, ...]:
    """Scan only the intake root; completed patient subfolders are never rescanned."""
    root = Path(intake_root)
    if not root.is_dir():
        return ()
    result: list[tuple[int, str, Path]] = []
    try:
        entries = tuple(root.iterdir())
    except OSError:
        return ()
    for path in entries:
        if not path.is_file() or not desktop_intake_is_candidate_word_file(path):
            continue
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            continue
        result.append((stamp, path.name.lower(), path))
    result.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in result)


def desktop_intake_scan_primary_candidates(intake_root: str | Path) -> list[Path]:
    result: list[Path] = []
    for path in desktop_intake_iter_candidates(intake_root):
        if not desktop_intake_file_is_quiet(path):
            continue
        if desktop_intake_is_primary_document(path):
            result.append(path)
    return result


def _desktop_registry_path() -> Path | None:
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


def desktop_intake_discover_desktop() -> Path:
    """Resolve real Windows Desktop, including OneDrive-redirected profiles."""
    candidates: list[Path] = []
    registry = _desktop_registry_path()
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
    return Path.home() / "Desktop"


def desktop_intake_root_path() -> Path:
    return desktop_intake_discover_desktop() / DESKTOP_INTAKE_FOLDER_NAME


def desktop_intake_ensure_root() -> Path:
    root = desktop_intake_root_path()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _desktop_normalize_folder_settings(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    source = dict(settings or {})
    raw_parts = source.get("parts", DESKTOP_FOLDER_NAMING_DEFAULT["parts"])
    if not isinstance(raw_parts, (list, tuple)):
        raw_parts = DESKTOP_FOLDER_NAMING_DEFAULT["parts"]
    parts: list[str] = []
    for value in raw_parts:
        key = str(value or "").strip()
        if key in DESKTOP_FOLDER_NAMING_OPTIONS and key not in parts:
            parts.append(key)
    if not parts:
        parts = list(DESKTOP_FOLDER_NAMING_DEFAULT["parts"])
    date_format = str(source.get("date_format", "short") or "short").strip().lower()
    if date_format not in {"short", "full"}:
        date_format = "short"
    return {"parts": parts, "date_format": date_format}


def _desktop_sanitize_folder_component(
    value: str,
    *,
    fallback: str = "Пациент",
    max_length: int = 120,
) -> str:
    text = _DESKTOP_INVALID_WINDOWS_CHARS_RE.sub(" ", str(value or ""))
    text = " ".join(text.split()).strip(" .")
    if not text:
        text = fallback
    if text.upper() in _DESKTOP_WINDOWS_RESERVED_NAMES:
        text = f"_{text}"
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    return text or fallback


def _desktop_parse_date(value: Any) -> date | None:
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


def _desktop_format_date(value: Any, *, date_format: str) -> str:
    parsed = _desktop_parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%d.%m.%y" if date_format == "short" else "%d.%m.%Y")


def _desktop_format_month(value: Any) -> str:
    parsed = _desktop_parse_date(value)
    if not parsed:
        return ""
    return f"{_DESKTOP_RUSSIAN_MONTHS[parsed.month - 1]} {parsed.year}"


def _desktop_fio_tokens(fio: str) -> list[str]:
    return [token for token in re.split(r"\s+", str(fio or "").strip()) if token]


def _desktop_looks_like_human_fio(value: str) -> bool:
    tokens = [token.strip(" ,:;") for token in _desktop_fio_tokens(value)]
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    if {token.casefold().strip(".") for token in tokens} & _DESKTOP_BAD_FIO_WORDS:
        return False
    if any(any(char.isdigit() for char in token) for token in tokens):
        return False
    if not _DESKTOP_HUMAN_NAME_PART_RE.fullmatch(tokens[0]):
        return False
    return all(
        _DESKTOP_HUMAN_NAME_PART_RE.fullmatch(token) or _DESKTOP_INITIALS_RE.fullmatch(token)
        for token in tokens[1:]
    )


def _desktop_surname_initials(fio: str) -> str:
    tokens = _desktop_fio_tokens(fio)
    if not tokens:
        return ""
    surname = tokens[0]
    initials: list[str] = []
    for token in tokens[1:]:
        letters = re.findall(r"(?:^|\.)([A-Za-zА-ЯЁа-яё])(?=\.|$)", token)
        if len(letters) >= 2:
            initials.extend(letter.upper() + "." for letter in letters[: 2 - len(initials)])
        elif token.strip("."):
            initials.append(token.strip(".")[0].upper() + ".")
        if len(initials) >= 2:
            break
    return f"{surname} {''.join(initials)}".strip()


def desktop_build_patient_folder_name(
    *,
    fio: str,
    admission_date: Any = "",
    discharge_date: Any = "",
    fallback_stem: str = "Пациент",
    settings: Mapping[str, Any] | None = None,
) -> str:
    """Build a Dokkomplekt-compatible, Windows-safe patient folder name."""
    config = _desktop_normalize_folder_settings(settings)
    date_format = str(config["date_format"])
    fio_tokens = _desktop_fio_tokens(fio)
    surname_name = " ".join(fio_tokens[:2])
    values = {
        "full_fio": str(fio or "").strip(),
        "surname_initials": _desktop_surname_initials(fio),
        "surname_name": surname_name,
        "admission_date": _desktop_format_date(admission_date, date_format=date_format),
        "discharge_date": _desktop_format_date(discharge_date, date_format=date_format),
        "admission_discharge_dates": " — ".join(
            part
            for part in (
                _desktop_format_date(admission_date, date_format=date_format),
                _desktop_format_date(discharge_date, date_format=date_format),
            )
            if part
        ),
        "admission_month": _desktop_format_month(admission_date),
        "discharge_month": _desktop_format_month(discharge_date),
    }
    selected = [values[key] for key in config["parts"] if values.get(key)]
    raw = " ".join(selected).strip() or str(fallback_stem or "Пациент")
    return _desktop_sanitize_folder_component(raw)


def _desktop_patient_folder_info(primary_path: str | Path) -> DesktopPatientFolderInfo:
    """Read only naming fields; never feed values back into document generation."""
    path = Path(primary_path)
    fio = ""
    try:
        from medical_parser import MedicalTextParser

        parsed = MedicalTextParser().parse_docx(str(path))
        candidate = str(getattr(parsed, "fio", "") or "").strip()
        if _desktop_looks_like_human_fio(candidate):
            fio = candidate
    except Exception:
        pass

    # Use the project's already-hardened title-date resolver for the folder
    # name.  It rejects demographic/birth-date context.  If it finds no safe
    # admission/title date, omitting the month is safer than inventing one.
    admission_date = ""
    try:
        from medical_docx_title_dates import extract_admission_date_from_title_docx

        admission_date = str(extract_admission_date_from_title_docx(path) or "").strip()
    except Exception:
        pass

    folder_name = desktop_build_patient_folder_name(
        fio=fio,
        admission_date=admission_date,
        fallback_stem=path.stem,
    )
    return DesktopPatientFolderInfo(fio=fio, admission_date=admission_date, folder_name=folder_name)


def _desktop_sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _desktop_same_file_content(path: Path, digest: str) -> bool:
    try:
        return path.is_file() and _desktop_sha256_file(path) == digest
    except OSError:
        return False


def _desktop_folder_contains_digest(folder: Path, digest: str) -> Path | None:
    if not folder.is_dir():
        return None
    try:
        entries = tuple(folder.iterdir())
    except OSError:
        return None
    for child in entries:
        if child.is_file() and desktop_intake_is_candidate_word_file(child):
            if _desktop_same_file_content(child, digest):
                return child
    return None


def _desktop_patient_folder_candidates(root: Path, base_name: str) -> Iterable[Path]:
    yield root / base_name
    for index in range(2, 1000):
        yield root / f"{base_name} ({index})"


def _desktop_allocate_patient_folder(
    root: Path,
    base_name: str,
    source_digest: str,
) -> tuple[Path, Path | None]:
    for folder in _desktop_patient_folder_candidates(root, base_name):
        if not folder.exists():
            folder.mkdir(parents=False, exist_ok=False)
            return folder, None
        existing = _desktop_folder_contains_digest(folder, source_digest)
        if existing is not None:
            return folder, existing
    raise RuntimeError("Не удалось подобрать свободную подпапку пациента")


def _desktop_available_destination(folder: Path, filename: str) -> Path:
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


def desktop_intake_prepare_patient_folder(
    source_path: str | Path,
    *,
    intake_root: str | Path | None = None,
    folder_name: str | None = None,
) -> Path:
    """Move the primary into its episode folder; never edit the document itself."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not desktop_intake_is_candidate_word_file(source):
        raise ValueError(f"Неподдерживаемый первичный документ: {source.name}")

    root = Path(intake_root) if intake_root is not None else desktop_intake_ensure_root()
    root.mkdir(parents=True, exist_ok=True)
    info = _desktop_patient_folder_info(source)
    base_name = _desktop_sanitize_folder_component(folder_name or info.folder_name)
    source_digest = _desktop_sha256_file(source)
    patient_folder, existing_primary = _desktop_allocate_patient_folder(root, base_name, source_digest)

    if existing_primary is not None:
        try:
            if source.resolve() != existing_primary.resolve():
                source.unlink()
        except OSError:
            pass
        return existing_primary

    destination = _desktop_available_destination(patient_folder, source.name)
    try:
        os.replace(source, destination)
    except OSError:
        try:
            shutil.move(str(source), str(destination))
        except OSError:
            shutil.copy2(source, destination)
            source.unlink()
    return destination


# ---------------------------------------------------------------------------
# Hidden per-user watcher and update handoff
# ---------------------------------------------------------------------------


def _desktop_gui_heartbeat_path() -> Path:
    return _desktop_runtime_dir() / "desktop-intake-gui.heartbeat"


def _desktop_touch_gui_heartbeat() -> None:
    tmp: Path | None = None
    try:
        path = _desktop_gui_heartbeat_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(f"{time.time():.6f}\n", encoding="ascii")
        os.replace(tmp, path)
    except OSError:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def _desktop_gui_is_active() -> bool:
    try:
        value = float(_desktop_gui_heartbeat_path().read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return False
    return 0.0 <= time.time() - value <= _DESKTOP_INTAKE_HEARTBEAT_MAX_AGE_SECONDS


def _desktop_runtime_command(*arguments: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), *arguments]

    executable = Path(sys.executable).resolve()
    if os.name == "nt" and executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.is_file():
            executable = pythonw
    main_py = Path(__file__).resolve().with_name("main.py")
    return [str(executable), str(main_py), *arguments]


def _desktop_native_gui_command() -> list[str]:
    return _desktop_runtime_command()


def _desktop_current_agent_identity() -> str:
    raw = "\0".join(_desktop_native_gui_command()).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()


def _desktop_agent_handoff_path() -> Path:
    return _desktop_runtime_dir() / "desktop-intake-agent-handoff.json"


def _desktop_write_agent_handoff() -> None:
    payload = {
        "schema": _DESKTOP_INTAKE_HANDOFF_SCHEMA,
        "identity": _desktop_current_agent_identity(),
        "gui_command": _desktop_native_gui_command(),
    }
    path = _desktop_agent_handoff_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _desktop_read_agent_handoff() -> dict[str, object] | None:
    try:
        payload = json.loads(_desktop_agent_handoff_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != _DESKTOP_INTAKE_HANDOFF_SCHEMA:
        return None
    identity = payload.get("identity")
    command = payload.get("gui_command")
    if not isinstance(identity, str) or not identity:
        return None
    if not isinstance(command, list) or not command:
        return None
    if not all(isinstance(item, str) and item for item in command):
        return None
    return payload


def _desktop_command_target_exists(command: list[str]) -> bool:
    try:
        if not Path(command[0]).is_file():
            return False
        if len(command) >= 2 and command[1].lower().endswith((".py", ".pyw")):
            return Path(command[1]).is_file()
        return True
    except OSError:
        return False


def _desktop_launch_command() -> list[str]:
    handoff = _desktop_read_agent_handoff()
    if handoff is not None:
        command = [str(item) for item in handoff["gui_command"]]  # type: ignore[index]
        if _desktop_command_target_exists(command):
            return command
    return _desktop_native_gui_command()


def _desktop_agent_is_retired() -> bool:
    handoff = _desktop_read_agent_handoff()
    if handoff is None:
        return False
    return str(handoff["identity"]) != _desktop_current_agent_identity()


def _desktop_hidden_popen(command: list[str]) -> subprocess.Popen[bytes]:
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        flags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
        kwargs["creationflags"] = flags
    return subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]


def _desktop_startup_script_path() -> Path | None:
    if os.name != "nt":
        return None
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return None
    startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "MedicalDiaryAutofill Intake.vbs"


def desktop_intake_startup_vbs_payload(command: list[str]) -> str:
    """Build WSH-safe UTF-16 script content; paths may contain Cyrillic."""
    command_line = subprocess.list2cmdline(command)
    escaped = command_line.replace('"', '""')
    return (
        "On Error Resume Next\r\n"
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.Run "{escaped}", 0, False\r\n'
    )


def _desktop_install_agent_autostart() -> bool:
    if os.name != "nt" or os.environ.get("CI", "").strip():
        return False
    path = _desktop_startup_script_path()
    if path is None:
        return False
    try:
        _desktop_write_agent_handoff()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = desktop_intake_startup_vbs_payload(
            _desktop_runtime_command(DESKTOP_INTAKE_AGENT_ARGUMENT)
        )
        if path.is_file():
            try:
                if path.read_text(encoding="utf-16") == payload:
                    return True
            except (OSError, UnicodeError):
                pass
        tmp = path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-16")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _desktop_start_agent_process() -> bool:
    if os.name != "nt" or os.environ.get("CI", "").strip():
        return False
    try:
        _desktop_write_agent_handoff()
        _desktop_hidden_popen(_desktop_runtime_command(DESKTOP_INTAKE_AGENT_ARGUMENT))
        return True
    except OSError:
        return False


def _desktop_agent_log(message: str) -> None:
    """Bounded technical log.  Never include FIO or patient filenames."""
    try:
        path = _desktop_runtime_dir() / "desktop-intake-agent.log"
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
        if path.exists() and path.stat().st_size > _DESKTOP_INTAKE_MAX_LOG_BYTES:
            path.write_text("", encoding="utf-8")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line)
    except OSError:
        pass


def _desktop_acquire_agent_mutex_once() -> int | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    create_mutex.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    handle = create_mutex(None, False, _DESKTOP_INTAKE_AGENT_MUTEX_NAME)
    if not handle:
        return None
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return int(handle)


def _desktop_acquire_agent_mutex() -> int | None:
    deadline = time.monotonic() + _DESKTOP_INTAKE_AGENT_MUTEX_HANDOFF_SECONDS
    while True:
        handle = _desktop_acquire_agent_mutex_once()
        if handle is not None:
            return handle
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.4)


def _desktop_release_agent_mutex(handle: int | None) -> None:
    if os.name != "nt" or not handle:
        return
    try:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(ctypes.c_void_p(handle))
    except Exception:
        pass


def _desktop_source_signature(path: Path) -> str:
    try:
        stat = path.stat()
        raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode(
            "utf-8", errors="surrogatepass"
        )
    except OSError:
        raw = str(path).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()


def _desktop_launch_gui_for_primary(path: Path) -> bool:
    try:
        _desktop_hidden_popen(
            [*_desktop_launch_command(), DESKTOP_INTAKE_PRIMARY_ARGUMENT, str(path.resolve())]
        )
        return True
    except OSError:
        return False


def run_desktop_intake_agent() -> int:
    """Run hidden watcher.  This mode never imports or executes generation code."""
    if os.name != "nt":
        return 0
    handle = _desktop_acquire_agent_mutex()
    if handle is None:
        return 0

    recently_launched: dict[str, float] = {}
    try:
        root = desktop_intake_ensure_root()
        _desktop_agent_log("agent started")
        while True:
            if _desktop_agent_is_retired():
                _desktop_agent_log("agent retired after application update")
                return 0

            now = time.time()
            recently_launched = {
                signature: launched_at
                for signature, launched_at in recently_launched.items()
                if now - launched_at < _DESKTOP_INTAKE_AGENT_RELAUNCH_COOLDOWN_SECONDS
            }
            if not _desktop_gui_is_active():
                for path in desktop_intake_scan_primary_candidates(root):
                    signature = _desktop_source_signature(path)
                    if signature in recently_launched:
                        continue
                    if _desktop_launch_gui_for_primary(path):
                        recently_launched[signature] = now
                        _desktop_agent_log("primary detected; GUI launch requested")
                    else:
                        _desktop_agent_log("primary detected; GUI launch failed")
                    break
            time.sleep(_DESKTOP_INTAKE_AGENT_POLL_SECONDS)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        _desktop_agent_log(f"agent stopped after {type(exc).__name__}")
        return 1
    finally:
        _desktop_release_agent_mutex(handle)


# ---------------------------------------------------------------------------
# Existing-GUI handoff
# ---------------------------------------------------------------------------


def _desktop_show_intake_error(app, text: str) -> None:
    try:
        messagebox.showerror("Выписанные пациенты", text, parent=app.root)
    except Exception:
        pass


def _desktop_process_primary(app, source_path: str | Path) -> bool:
    source = Path(source_path)
    if not source.is_file():
        return False
    if not desktop_intake_file_is_quiet(source):
        return False
    if not desktop_intake_is_primary_document(source):
        return False
    try:
        moved_primary = desktop_intake_prepare_patient_folder(source)
        # This is the hard architecture boundary.  From here onward the exact
        # pre-existing diary-filler path owns parsing, popups and generation.
        app._apply_primary_document_path(str(moved_primary), prompt_for_referral=True)
        try:
            app.root.deiconify()
            app.root.lift()
            app.root.focus_force()
        except Exception:
            pass
        return True
    except Exception as exc:
        _desktop_show_intake_error(
            app,
            "Не удалось обработать первичный документ из папки «Выписанные пациенты».\n\n"
            f"{type(exc).__name__}: {exc}",
        )
        return False


def _desktop_schedule_heartbeat(app) -> None:
    try:
        if not app.root.winfo_exists():
            return
        _desktop_touch_gui_heartbeat()
        app.root.after(_DESKTOP_INTAKE_HEARTBEAT_MS, lambda: _desktop_schedule_heartbeat(app))
    except Exception:
        return


def _desktop_poll_intake(app, intake_root: Path) -> None:
    try:
        if not app.root.winfo_exists():
            return
        if not getattr(app, "_desktop_intake_processing", False):
            candidates = desktop_intake_scan_primary_candidates(intake_root)
            if candidates:
                app._desktop_intake_processing = True
                try:
                    _desktop_process_primary(app, candidates[0])
                finally:
                    app._desktop_intake_processing = False
        app.root.after(
            _DESKTOP_INTAKE_GUI_POLL_MS,
            lambda: _desktop_poll_intake(app, intake_root),
        )
    except Exception:
        try:
            app.root.after(
                _DESKTOP_INTAKE_GUI_POLL_MS,
                lambda: _desktop_poll_intake(app, intake_root),
            )
        except Exception:
            pass


def start_desktop_intake_runtime(app, *, initial_primary: str | Path | None = None) -> None:
    """Enable the optional patient-folder workflow without risking core startup.

    The convenience layer is fail-open by design.  A locked/redirected Desktop,
    broken Startup folder or antivirus interference must never prevent the
    original document application from opening and working manually.
    """
    if os.name != "nt":
        return
    if os.environ.get("MEDICAL_AUTOFILL_DISABLE_DESKTOP_INTAKE", "").strip() == "1":
        return

    try:
        _desktop_touch_gui_heartbeat()
        intake_root = desktop_intake_ensure_root()
        _desktop_install_agent_autostart()
        _desktop_start_agent_process()
    except Exception:
        return

    app._desktop_intake_processing = False
    _desktop_schedule_heartbeat(app)

    if initial_primary:
        app._desktop_intake_processing = True

        def process_initial() -> None:
            try:
                _desktop_process_primary(app, initial_primary)
            finally:
                app._desktop_intake_processing = False

        app.root.after(80, process_initial)

    app.root.after(
        _DESKTOP_INTAKE_GUI_POLL_MS,
        lambda: _desktop_poll_intake(app, intake_root),
    )
