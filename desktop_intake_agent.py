"""Background watcher for the ``Выписанные пациенты`` desktop intake folder.

The watcher is intentionally a mode of the same program/EXE.  It has no
medical generation logic and never edits a document.  When the GUI is closed
and a stable primary document appears, it launches the normal GUI with that
path.  When the GUI is already open, its own lightweight poller handles the
file and the agent stays idle.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

from desktop_intake import ensure_intake_root, scan_primary_candidates


AGENT_ARGUMENT = "--intake-agent"
PRIMARY_ARGUMENT = "--intake-primary"
_AGENT_MUTEX_NAME = "Local\\MedicalDiaryAutofillDesktopIntakeAgent"
_HEARTBEAT_MAX_AGE_SECONDS = 6.0
_AGENT_POLL_SECONDS = 2.0
_AGENT_RELAUNCH_COOLDOWN_SECONDS = 30.0
_MAX_LOG_BYTES = 128 * 1024


def _local_runtime_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA", "").strip() or os.environ.get("APPDATA", "").strip()
    base = Path(root) if root else Path.home() / ".medical_diary_autofill"
    path = base / "MedicalDiaryAutofill"
    path.mkdir(parents=True, exist_ok=True)
    return path


def gui_heartbeat_path() -> Path:
    return _local_runtime_dir() / "desktop-intake-gui.heartbeat"


def touch_gui_heartbeat() -> None:
    """Record GUI liveness without storing any patient data."""
    path = gui_heartbeat_path()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(f"{time.time():.6f}\n", encoding="ascii")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def gui_is_active(*, max_age_seconds: float = _HEARTBEAT_MAX_AGE_SECONDS) -> bool:
    try:
        value = float(gui_heartbeat_path().read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return False
    return 0.0 <= time.time() - value <= max_age_seconds


def _runtime_command(*arguments: str) -> list[str]:
    """Launch this same application in source or frozen PyInstaller form."""
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), *arguments]

    executable = Path(sys.executable).resolve()
    if os.name == "nt" and executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.is_file():
            executable = pythonw
    main_py = Path(__file__).resolve().with_name("main.py")
    return [str(executable), str(main_py), *arguments]


def _hidden_popen(command: list[str]) -> subprocess.Popen[bytes]:
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        flags = 0
        flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        flags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
        kwargs["creationflags"] = flags
    return subprocess.Popen(command, **kwargs)  # type: ignore[arg-type]


def _startup_script_path() -> Path | None:
    if os.name != "nt":
        return None
    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return None
    startup = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "MedicalDiaryAutofill Intake.vbs"


def install_agent_autostart() -> bool:
    """Install/update a per-user hidden Startup entry; no admin rights required."""
    if os.name != "nt" or os.environ.get("CI", "").strip():
        return False
    path = _startup_script_path()
    if path is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    command = subprocess.list2cmdline(_runtime_command(AGENT_ARGUMENT))
    escaped = command.replace('"', '""')
    payload = f'CreateObject("Wscript.Shell").Run "{escaped}", 0, False\r\n'
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == payload:
            return True
        tmp = path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def start_agent_process() -> bool:
    if os.name != "nt" or os.environ.get("CI", "").strip():
        return False
    try:
        _hidden_popen(_runtime_command(AGENT_ARGUMENT))
        return True
    except OSError:
        return False


def _log(message: str) -> None:
    """Best-effort bounded technical log.  Patient filenames are never logged."""
    path = _local_runtime_dir() / "desktop-intake-agent.log"
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    try:
        if path.exists() and path.stat().st_size > _MAX_LOG_BYTES:
            path.write_text("", encoding="utf-8")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line)
    except OSError:
        pass


def _acquire_agent_mutex() -> int | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    create_mutex.restype = ctypes.c_void_p
    handle = create_mutex(None, False, _AGENT_MUTEX_NAME)
    if not handle:
        return None
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return int(handle)


def _release_agent_mutex(handle: int | None) -> None:
    if os.name != "nt" or not handle:
        return
    try:
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(ctypes.c_void_p(handle))
    except Exception:
        pass


def _source_signature(path: Path) -> str:
    try:
        stat = path.stat()
        raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8", errors="surrogatepass")
    except OSError:
        raw = str(path).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()


def _launch_gui_for_primary(path: Path) -> bool:
    try:
        _hidden_popen(_runtime_command(PRIMARY_ARGUMENT, str(path.resolve())))
        return True
    except OSError:
        return False


def run_agent() -> int:
    """Run the hidden watcher until the user session ends."""
    if os.name != "nt":
        return 0
    handle = _acquire_agent_mutex()
    if handle is None:
        return 0

    recently_launched: dict[str, float] = {}
    try:
        root = ensure_intake_root()
        _log("agent started")
        while True:
            now = time.time()
            recently_launched = {
                signature: launched_at
                for signature, launched_at in recently_launched.items()
                if now - launched_at < _AGENT_RELAUNCH_COOLDOWN_SECONDS
            }

            if not gui_is_active():
                for path in scan_primary_candidates(root):
                    signature = _source_signature(path)
                    if signature in recently_launched:
                        continue
                    if _launch_gui_for_primary(path):
                        recently_launched[signature] = now
                        _log("primary detected; GUI launch requested")
                    else:
                        _log("primary detected; GUI launch failed")
                    break
            time.sleep(_AGENT_POLL_SECONDS)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        _log(f"agent stopped after {type(exc).__name__}")
        return 1
    finally:
        _release_agent_mutex(handle)
