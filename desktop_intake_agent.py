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
import json
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
_AGENT_MUTEX_HANDOFF_SECONDS = 8.0
_MAX_LOG_BYTES = 128 * 1024
_HANDOFF_SCHEMA = 1


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
    tmp: Path | None = None
    try:
        path = gui_heartbeat_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(f"{time.time():.6f}\n", encoding="ascii")
        os.replace(tmp, path)
    except OSError:
        if tmp is not None:
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


def _native_gui_command() -> list[str]:
    return _runtime_command()


def _current_agent_identity() -> str:
    """Stable identity of the install/source tree that owns this running agent."""
    raw = "\0".join(_native_gui_command()).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(raw).hexdigest()


def _handoff_path() -> Path:
    return _local_runtime_dir() / "desktop-intake-agent-handoff.json"


def _write_agent_handoff() -> None:
    """Publish the newest GUI launch target so stale agents can retire safely."""
    payload = {
        "schema": _HANDOFF_SCHEMA,
        "identity": _current_agent_identity(),
        "gui_command": _native_gui_command(),
    }
    path = _handoff_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_agent_handoff() -> dict[str, object] | None:
    try:
        payload = json.loads(_handoff_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != _HANDOFF_SCHEMA:
        return None
    command = payload.get("gui_command")
    identity = payload.get("identity")
    if not isinstance(identity, str) or not identity:
        return None
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        return None
    return payload


def _command_target_exists(command: list[str]) -> bool:
    try:
        if not Path(command[0]).is_file():
            return False
        # Source mode is [pythonw.exe, main.py].  A deleted source tree must not
        # be preferred merely because Python itself still exists.
        if len(command) >= 2 and command[1].lower().endswith((".py", ".pyw")):
            return Path(command[1]).is_file()
        return True
    except OSError:
        return False


def _launch_command() -> list[str]:
    """Prefer the newest installed GUI target, falling back to this process."""
    handoff = _read_agent_handoff()
    if handoff is not None:
        command = [str(item) for item in handoff["gui_command"]]  # type: ignore[index]
        if _command_target_exists(command):
            return command
    return _native_gui_command()


def _agent_is_retired() -> bool:
    """Return True when a newer/different install has taken ownership."""
    handoff = _read_agent_handoff()
    if handoff is None:
        return False
    return str(handoff["identity"]) != _current_agent_identity()


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


def _startup_vbs_payload(command: list[str]) -> str:
    command_line = subprocess.list2cmdline(command)
    escaped = command_line.replace('"', '""')
    return (
        "On Error Resume Next\r\n"
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.Run "{escaped}", 0, False\r\n'
    )


def install_agent_autostart() -> bool:
    """Install/update a per-user hidden Startup entry; no admin rights required.

    VBS is deliberately UTF-16 with BOM.  Windows Script Host is not reliably
    UTF-8-safe for Cyrillic profile/install paths on older Windows builds.
    """
    if os.name != "nt" or os.environ.get("CI", "").strip():
        return False
    path = _startup_script_path()
    if path is None:
        return False
    try:
        _write_agent_handoff()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _startup_vbs_payload(_runtime_command(AGENT_ARGUMENT))
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


def start_agent_process() -> bool:
    if os.name != "nt" or os.environ.get("CI", "").strip():
        return False
    try:
        # Keep the handoff fresh even if the Startup entry was already current.
        _write_agent_handoff()
        _hidden_popen(_runtime_command(AGENT_ARGUMENT))
        return True
    except OSError:
        return False


def _log(message: str) -> None:
    """Best-effort bounded technical log.  Patient filenames are never logged."""
    try:
        path = _local_runtime_dir() / "desktop-intake-agent.log"
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
        if path.exists() and path.stat().st_size > _MAX_LOG_BYTES:
            path.write_text("", encoding="utf-8")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(line)
    except OSError:
        pass


def _acquire_agent_mutex_once() -> int | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    create_mutex.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    handle = create_mutex(None, False, _AGENT_MUTEX_NAME)
    if not handle:
        return None
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return int(handle)


def _acquire_agent_mutex() -> int | None:
    """Allow a newly installed agent to take over after the stale owner retires."""
    deadline = time.monotonic() + _AGENT_MUTEX_HANDOFF_SECONDS
    while True:
        handle = _acquire_agent_mutex_once()
        if handle is not None:
            return handle
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.4)


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
        _hidden_popen([*_launch_command(), PRIMARY_ARGUMENT, str(path.resolve())])
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
            if _agent_is_retired():
                _log("agent retired after application update")
                return 0

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
