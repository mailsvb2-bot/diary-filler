"""Focused regressions for the outer Windows intake lifecycle.

This module must never generate or edit medical documents. It exercises only
watcher/folder lifecycle behavior that sits before the canonical
app._apply_primary_document_path(...) handoff.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import startup
import main as app_main


def assert_agent_recreates_deleted_intake_root() -> None:
    """A live watcher must heal a deleted intake folder instead of becoming inert."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / startup.DESKTOP_INTAKE_FOLDER_NAME
        root.mkdir()

        original_os = startup.os
        original_acquire = startup._desktop_acquire_agent_mutex
        original_release = startup._desktop_release_agent_mutex
        original_root_path = startup.desktop_intake_root_path
        original_touch = startup._desktop_touch_agent_heartbeat
        original_retired = startup._desktop_agent_is_retired
        original_gui_active = startup._desktop_gui_is_active
        original_scan = startup.desktop_intake_scan_wake_candidates
        original_sleep = startup.time.sleep
        original_log = startup._desktop_agent_log
        scans: list[bool] = []
        root_path_calls = 0

        def resolve_root() -> Path:
            nonlocal root_path_calls
            root_path_calls += 1
            return root

        def scan(candidate_root: str | Path) -> list[Path]:
            scans.append(Path(candidate_root).is_dir())
            if len(scans) == 1:
                root.rmdir()
                return []
            raise KeyboardInterrupt

        try:
            startup.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = lambda: 1  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = lambda _handle: None  # type: ignore[assignment]
            startup.desktop_intake_root_path = resolve_root  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = lambda: None  # type: ignore[assignment]
            startup._desktop_agent_is_retired = lambda: False  # type: ignore[assignment]
            startup._desktop_gui_is_active = lambda: False  # type: ignore[assignment]
            startup.desktop_intake_scan_wake_candidates = scan  # type: ignore[assignment]
            startup.time.sleep = lambda _seconds: None  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]

            assert startup.run_desktop_intake_agent() == 0
            assert root_path_calls >= 2, root_path_calls
            assert scans == [True, True], scans
            assert root.is_dir(), "watcher did not recreate deleted intake root"
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.time.sleep = original_sleep  # type: ignore[assignment]
            startup.desktop_intake_scan_wake_candidates = original_scan  # type: ignore[assignment]
            startup._desktop_gui_is_active = original_gui_active  # type: ignore[assignment]
            startup._desktop_agent_is_retired = original_retired  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = original_touch  # type: ignore[assignment]
            startup.desktop_intake_root_path = original_root_path  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = original_release  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = original_acquire  # type: ignore[assignment]
            startup.os = original_os  # type: ignore[assignment]


def assert_agent_rebinds_when_desktop_moves() -> None:
    """An existing old Desktop directory must not pin the live watcher forever."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        first = base / "Desktop-A" / startup.DESKTOP_INTAKE_FOLDER_NAME
        second = base / "Desktop-B" / startup.DESKTOP_INTAKE_FOLDER_NAME
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        active = {"root": first}
        scans: list[Path] = []

        original_os = startup.os
        original_root_path = startup.desktop_intake_root_path
        original_acquire = startup._desktop_acquire_agent_mutex
        original_release = startup._desktop_release_agent_mutex
        original_touch = startup._desktop_touch_agent_heartbeat
        original_retired = startup._desktop_agent_is_retired
        original_gui_active = startup._desktop_gui_is_active
        original_scan = startup.desktop_intake_scan_wake_candidates
        original_sleep = startup.time.sleep
        original_log = startup._desktop_agent_log

        def scan(candidate_root: str | Path) -> list[Path]:
            scans.append(Path(candidate_root))
            if len(scans) == 1:
                active["root"] = second
                return []
            raise KeyboardInterrupt

        try:
            startup.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            startup.desktop_intake_root_path = lambda: active["root"]  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = lambda: 1  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = lambda _handle: None  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = lambda: None  # type: ignore[assignment]
            startup._desktop_agent_is_retired = lambda: False  # type: ignore[assignment]
            startup._desktop_gui_is_active = lambda: False  # type: ignore[assignment]
            startup.desktop_intake_scan_wake_candidates = scan  # type: ignore[assignment]
            startup.time.sleep = lambda _seconds: None  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]

            assert startup.run_desktop_intake_agent() == 0
            assert scans == [first, second], scans
            assert first.is_dir(), "old Desktop intentionally remains present in this regression"
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.time.sleep = original_sleep  # type: ignore[assignment]
            startup.desktop_intake_scan_wake_candidates = original_scan  # type: ignore[assignment]
            startup._desktop_gui_is_active = original_gui_active  # type: ignore[assignment]
            startup._desktop_agent_is_retired = original_retired  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = original_touch  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = original_release  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = original_acquire  # type: ignore[assignment]
            startup.desktop_intake_root_path = original_root_path  # type: ignore[assignment]
            startup.os = original_os  # type: ignore[assignment]


def assert_gui_poll_rebinds_when_desktop_moves() -> None:
    """An already-open GUI must poll the current Desktop, not a stale root."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        old_root = base / "Desktop-A" / startup.DESKTOP_INTAKE_FOLDER_NAME
        new_root = base / "Desktop-B" / startup.DESKTOP_INTAKE_FOLDER_NAME
        old_root.mkdir(parents=True)
        new_root.mkdir(parents=True)
        scanned: list[Path] = []

        class RootStub:
            def winfo_exists(self) -> bool:
                return True

            def after(self, _delay: int, _callback) -> None:
                return None

        app = SimpleNamespace(
            root=RootStub(),
            _desktop_intake_processing=False,
            _desktop_intake_observed={},
        )
        original_root_path = startup.desktop_intake_root_path
        original_snapshot = startup._desktop_candidate_snapshot
        original_log = startup._desktop_agent_log
        try:
            startup.desktop_intake_root_path = lambda: new_root  # type: ignore[assignment]
            startup._desktop_candidate_snapshot = (
                lambda root: scanned.append(Path(root)) or {}
            )  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]
            startup._desktop_poll_intake(app, old_root)
            assert scanned == [new_root], scanned
            assert app._desktop_intake_observed == {}
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup._desktop_candidate_snapshot = original_snapshot  # type: ignore[assignment]
            startup.desktop_intake_root_path = original_root_path  # type: ignore[assignment]


def assert_gui_poll_processes_only_new_or_changed_arrivals() -> None:
    """Unchanged intake files must never be re-parsed on every Tk polling tick."""
    candidate = Path("C:/intake/primary.docx")
    snapshots = [
        {"k": (candidate, "sig-1")},
        {"k": (candidate, "sig-1")},
        {"k": (candidate, "sig-2")},
        {},
        {"k": (candidate, "sig-2")},
    ]
    processed: list[Path] = []

    class RootStub:
        def winfo_exists(self) -> bool:
            return True

        def after(self, _delay: int, _callback) -> None:
            return None

    app = SimpleNamespace(
        root=RootStub(),
        _desktop_intake_processing=False,
        _desktop_intake_observed={},
    )
    original_rebind = startup._desktop_rebind_intake_root
    original_snapshot = startup._desktop_candidate_snapshot
    original_process = startup._desktop_process_primary
    original_log = startup._desktop_agent_log
    try:
        startup._desktop_rebind_intake_root = lambda root: (Path(root), False)  # type: ignore[assignment]
        startup._desktop_candidate_snapshot = lambda _root: snapshots.pop(0)  # type: ignore[assignment]
        startup._desktop_process_primary = lambda _app, path: processed.append(Path(path)) or False  # type: ignore[assignment]
        startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]

        root = Path("C:/intake")
        startup._desktop_poll_intake(app, root)
        startup._desktop_poll_intake(app, root)
        startup._desktop_poll_intake(app, root)
        startup._desktop_poll_intake(app, root)
        startup._desktop_poll_intake(app, root)

        assert processed == [candidate, candidate, candidate], processed
        # first arrival, changed revision, then same revision after path removal/re-copy
    finally:
        startup._desktop_agent_log = original_log  # type: ignore[assignment]
        startup._desktop_process_primary = original_process  # type: ignore[assignment]
        startup._desktop_candidate_snapshot = original_snapshot  # type: ignore[assignment]
        startup._desktop_rebind_intake_root = original_rebind  # type: ignore[assignment]


def assert_old_watcher_retires_after_in_place_update() -> None:
    """Replacing the EXE at the same path must retire the old in-memory watcher."""
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        exe = runtime / "MedicalDiaryAutofill.exe"
        exe.write_bytes(b"same-path-old-build")
        command = [str(exe)]

        original_runtime_dir = startup._desktop_runtime_dir
        original_native_command = startup._desktop_native_gui_command
        original_identity_cache = startup._DESKTOP_AGENT_IDENTITY_CACHE
        try:
            startup._desktop_runtime_dir = lambda: runtime  # type: ignore[assignment]
            startup._desktop_native_gui_command = lambda: command  # type: ignore[assignment]

            old_identity = startup._desktop_build_agent_identity(command)
            startup._DESKTOP_AGENT_IDENTITY_CACHE = old_identity
            assert startup._desktop_current_agent_identity() == old_identity

            exe.write_bytes(b"same-path-new-build")
            new_identity = startup._desktop_build_agent_identity(command)
            assert old_identity != new_identity, (old_identity, new_identity)

            startup._DESKTOP_AGENT_IDENTITY_CACHE = new_identity
            startup._desktop_write_agent_handoff()
            startup._DESKTOP_AGENT_IDENTITY_CACHE = old_identity

            assert startup._desktop_agent_is_retired() is True
            assert startup._desktop_launch_command() == command
        finally:
            startup._DESKTOP_AGENT_IDENTITY_CACHE = original_identity_cache
            startup._desktop_native_gui_command = original_native_command  # type: ignore[assignment]
            startup._desktop_runtime_dir = original_runtime_dir  # type: ignore[assignment]



def assert_gui_launch_handoff_preserves_queued_arrivals() -> None:
    """Watcher baseline must ignore stale files without swallowing a second arrival."""
    stale = Path("stale.docx")
    first = Path("first.docx")
    second = Path("second.docx")
    current = {
        "stale-key": (stale, "sig-stale"),
        "first-key": (first, "sig-first"),
        "second-key": (second, "sig-second"),
    }
    handed = {
        startup._desktop_launch_observed_key("stale-key"): "sig-stale",
        startup._desktop_launch_observed_key("first-key"): "sig-first",
    }
    original_read = startup._desktop_read_gui_launch_observed
    try:
        startup._desktop_read_gui_launch_observed = lambda: dict(handed)  # type: ignore[assignment]
        observed = startup._desktop_gui_observed_from_launch_handoff(current)
    finally:
        startup._desktop_read_gui_launch_observed = original_read  # type: ignore[assignment]
    assert observed == {"stale-key": "sig-stale", "first-key": "sig-first"}, observed
    assert "second-key" not in observed, observed


def assert_agent_suppresses_duplicate_gui_launch_until_heartbeat() -> None:
    """Two quick arrivals must not spawn two visible GUI processes during startup."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / startup.DESKTOP_INTAKE_FOLDER_NAME
        root.mkdir()
        first = root / "first.docx"
        second = root / "second.docx"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        snapshots = [
            {},
            {"first": (first, "sig-first"), "second": (second, "sig-second")},
            {"first": (first, "sig-first"), "second": (second, "sig-second")},
        ]
        launches: list[Path] = []
        gui_states = iter([False, False])
        now = {"value": 100.0}
        sleeps = 0

        original_os = startup.os
        original_acquire = startup._desktop_acquire_agent_mutex
        original_release = startup._desktop_release_agent_mutex
        original_root = startup.desktop_intake_ensure_root
        original_rebind = startup._desktop_rebind_intake_root
        original_touch = startup._desktop_touch_agent_heartbeat
        original_retired = startup._desktop_agent_is_retired
        original_gui = startup._desktop_gui_is_active
        original_snapshot = startup._desktop_candidate_snapshot
        original_launch = startup._desktop_launch_gui_for_primary
        original_write_launch_observed = startup._desktop_write_gui_launch_observed
        original_sleep = startup.time.sleep
        original_monotonic = startup.time.monotonic
        original_log = startup._desktop_agent_log
        launch_handoffs: list[dict[str, str]] = []

        def snapshot(_root):
            if snapshots:
                return snapshots.pop(0)
            return {"first": (first, "sig-first"), "second": (second, "sig-second")}

        def sleep(_seconds):
            nonlocal sleeps
            sleeps += 1
            now["value"] += 0.5
            if sleeps >= 2:
                raise KeyboardInterrupt

        try:
            startup.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = lambda: 1  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = lambda _handle: None  # type: ignore[assignment]
            startup.desktop_intake_ensure_root = lambda: root  # type: ignore[assignment]
            startup._desktop_rebind_intake_root = lambda current: (Path(current), False)  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = lambda: None  # type: ignore[assignment]
            startup._desktop_agent_is_retired = lambda: False  # type: ignore[assignment]
            startup._desktop_gui_is_active = lambda: next(gui_states, False)  # type: ignore[assignment]
            startup._desktop_candidate_snapshot = snapshot  # type: ignore[assignment]
            startup._desktop_launch_gui_for_primary = lambda path: launches.append(Path(path)) or True  # type: ignore[assignment]
            startup._desktop_write_gui_launch_observed = lambda observed: launch_handoffs.append(dict(observed))  # type: ignore[assignment]
            startup.time.monotonic = lambda: now["value"]  # type: ignore[assignment]
            startup.time.sleep = sleep  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]

            assert startup.run_desktop_intake_agent() == 0
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.time.sleep = original_sleep  # type: ignore[assignment]
            startup.time.monotonic = original_monotonic  # type: ignore[assignment]
            startup._desktop_write_gui_launch_observed = original_write_launch_observed  # type: ignore[assignment]
            startup._desktop_launch_gui_for_primary = original_launch  # type: ignore[assignment]
            startup._desktop_candidate_snapshot = original_snapshot  # type: ignore[assignment]
            startup._desktop_gui_is_active = original_gui  # type: ignore[assignment]
            startup._desktop_agent_is_retired = original_retired  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = original_touch  # type: ignore[assignment]
            startup._desktop_rebind_intake_root = original_rebind  # type: ignore[assignment]
            startup.desktop_intake_ensure_root = original_root  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = original_release  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = original_acquire  # type: ignore[assignment]
            startup.os = original_os  # type: ignore[assignment]

        assert launches == [first], launches
        assert launch_handoffs == [{"first": "sig-first"}], launch_handoffs


def assert_agent_retries_failed_visible_launch() -> None:
    """A transient Popen failure must not permanently consume a user's file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / startup.DESKTOP_INTAKE_FOLDER_NAME
        root.mkdir()
        candidate = root / "patient.docx"
        candidate.write_bytes(b"patient")
        snapshots = [{}, {"k": (candidate, "sig")}, {"k": (candidate, "sig")}, {"k": (candidate, "sig")}]
        outcomes = iter([False, True])
        attempts: list[Path] = []
        now = {"value": 100.0}
        sleeps = 0

        original_os = startup.os
        original_acquire = startup._desktop_acquire_agent_mutex
        original_release = startup._desktop_release_agent_mutex
        original_root = startup.desktop_intake_ensure_root
        original_rebind = startup._desktop_rebind_intake_root
        original_touch = startup._desktop_touch_agent_heartbeat
        original_retired = startup._desktop_agent_is_retired
        original_gui = startup._desktop_gui_is_active
        original_snapshot = startup._desktop_candidate_snapshot
        original_launch = startup._desktop_launch_gui_for_primary
        original_write_launch_observed = startup._desktop_write_gui_launch_observed
        original_sleep = startup.time.sleep
        original_monotonic = startup.time.monotonic
        original_log = startup._desktop_agent_log

        def snapshot(_root):
            return snapshots.pop(0) if snapshots else {"k": (candidate, "sig")}

        def launch(path):
            attempts.append(Path(path))
            return next(outcomes)

        def sleep(_seconds):
            nonlocal sleeps
            sleeps += 1
            now["value"] += 1.1
            if sleeps >= 3:
                raise KeyboardInterrupt

        try:
            startup.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = lambda: 1  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = lambda _handle: None  # type: ignore[assignment]
            startup.desktop_intake_ensure_root = lambda: root  # type: ignore[assignment]
            startup._desktop_rebind_intake_root = lambda current: (Path(current), False)  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = lambda: None  # type: ignore[assignment]
            startup._desktop_agent_is_retired = lambda: False  # type: ignore[assignment]
            startup._desktop_gui_is_active = lambda: False  # type: ignore[assignment]
            startup._desktop_candidate_snapshot = snapshot  # type: ignore[assignment]
            startup._desktop_launch_gui_for_primary = launch  # type: ignore[assignment]
            startup._desktop_write_gui_launch_observed = lambda _observed: None  # type: ignore[assignment]
            startup.time.monotonic = lambda: now["value"]  # type: ignore[assignment]
            startup.time.sleep = sleep  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]

            assert startup.run_desktop_intake_agent() == 0
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.time.sleep = original_sleep  # type: ignore[assignment]
            startup.time.monotonic = original_monotonic  # type: ignore[assignment]
            startup._desktop_write_gui_launch_observed = original_write_launch_observed  # type: ignore[assignment]
            startup._desktop_launch_gui_for_primary = original_launch  # type: ignore[assignment]
            startup._desktop_candidate_snapshot = original_snapshot  # type: ignore[assignment]
            startup._desktop_gui_is_active = original_gui  # type: ignore[assignment]
            startup._desktop_agent_is_retired = original_retired  # type: ignore[assignment]
            startup._desktop_touch_agent_heartbeat = original_touch  # type: ignore[assignment]
            startup._desktop_rebind_intake_root = original_rebind  # type: ignore[assignment]
            startup.desktop_intake_ensure_root = original_root  # type: ignore[assignment]
            startup._desktop_release_agent_mutex = original_release  # type: ignore[assignment]
            startup._desktop_acquire_agent_mutex = original_acquire  # type: ignore[assignment]
            startup.os = original_os  # type: ignore[assignment]

        assert attempts == [candidate, candidate], attempts


def assert_desktop_intake_propagates_rejected_primary() -> None:
    """A safely moved source must not be reported as loaded when app parsing rejected it."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "candidate.docx"
        source.write_bytes(b"candidate")
        apply_calls: list[Path] = []
        logs: list[str] = []

        class RootStub:
            def deiconify(self):
                raise AssertionError("rejected primary must not continue to activation")

            def lift(self):
                raise AssertionError("rejected primary must not continue to activation")

            def focus_force(self):
                raise AssertionError("rejected primary must not continue to activation")

        class AppStub:
            root = RootStub()

            def _apply_primary_document_path(self, path, **_kwargs):
                apply_calls.append(Path(path))
                return False

        original_quiet = startup.desktop_intake_file_is_quiet
        original_classifier = startup.desktop_intake_is_primary_document
        original_prepare = startup.desktop_intake_prepare_patient_folder
        original_log = startup._desktop_agent_log
        try:
            startup.desktop_intake_file_is_quiet = lambda _path: True  # type: ignore[assignment]
            startup.desktop_intake_is_primary_document = lambda _path: True  # type: ignore[assignment]
            startup.desktop_intake_prepare_patient_folder = (  # type: ignore[assignment]
                lambda path, **_kwargs: Path(path)
            )
            startup._desktop_agent_log = lambda message: logs.append(str(message))  # type: ignore[assignment]
            assert startup._desktop_process_primary(AppStub(), source) is False
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.desktop_intake_prepare_patient_folder = original_prepare  # type: ignore[assignment]
            startup.desktop_intake_is_primary_document = original_classifier  # type: ignore[assignment]
            startup.desktop_intake_file_is_quiet = original_quiet  # type: ignore[assignment]

        assert apply_calls == [source], apply_calls
        assert any("rejected by application parsing" in item for item in logs), logs


def assert_unrecognized_word_arrival_gets_one_visible_explanation() -> None:
    """A wake-up that cannot be classified must not look like a silent no-op."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "unknown.docx"
        source.write_bytes(b"unknown")
        warnings: list[tuple[str, str]] = []
        app = SimpleNamespace(root=object())
        original_quiet = startup.desktop_intake_file_is_quiet
        original_classifier = startup.desktop_intake_is_primary_document
        original_warning = startup.messagebox.showwarning
        try:
            startup.desktop_intake_file_is_quiet = lambda _path: True  # type: ignore[assignment]
            startup.desktop_intake_is_primary_document = lambda _path: False  # type: ignore[assignment]
            startup.messagebox.showwarning = lambda title, message, **_kwargs: warnings.append((title, message))  # type: ignore[assignment]
            assert startup._desktop_process_primary(app, source) is False
        finally:
            startup.messagebox.showwarning = original_warning
            startup.desktop_intake_is_primary_document = original_classifier  # type: ignore[assignment]
            startup.desktop_intake_file_is_quiet = original_quiet  # type: ignore[assignment]
        assert len(warnings) == 1, warnings
        assert "не смогла надёжно распознать" in warnings[0][1], warnings
        assert source.is_file(), "unrecognized file must stay untouched"


def assert_pyinstaller_children_are_independent_and_gui_is_visible() -> None:
    """Persistent watcher must not hold the GUI's _MEI dir; GUI launch must not be detached."""
    captured: list[tuple[list[str], dict[str, object]]] = []
    original_os = startup.os
    original_popen = startup.subprocess.Popen
    had_detached = hasattr(startup.subprocess, "DETACHED_PROCESS")
    original_detached = getattr(startup.subprocess, "DETACHED_PROCESS", None)
    had_group = hasattr(startup.subprocess, "CREATE_NEW_PROCESS_GROUP")
    original_group = getattr(startup.subprocess, "CREATE_NEW_PROCESS_GROUP", None)
    had_frozen = hasattr(startup.sys, "frozen")
    original_frozen = getattr(startup.sys, "frozen", None)

    class PopenStub:
        pass

    def fake_popen(command, **kwargs):
        captured.append((list(command), dict(kwargs)))
        return PopenStub()

    try:
        startup.os = SimpleNamespace(name="nt", environ={"BASE": "1"})  # type: ignore[assignment]
        startup.subprocess.DETACHED_PROCESS = 0x00000008  # type: ignore[attr-defined]
        startup.subprocess.CREATE_NEW_PROCESS_GROUP = 0x00000200  # type: ignore[attr-defined]
        startup.sys.frozen = True  # type: ignore[attr-defined]
        startup.subprocess.Popen = fake_popen  # type: ignore[assignment]
        startup._desktop_hidden_popen(["app.exe", startup.DESKTOP_INTAKE_AGENT_ARGUMENT])
        startup._desktop_visible_popen(["app.exe", startup.DESKTOP_INTAKE_PRIMARY_ARGUMENT, "patient.docx"])
    finally:
        startup.subprocess.Popen = original_popen  # type: ignore[assignment]
        if had_detached:
            startup.subprocess.DETACHED_PROCESS = original_detached  # type: ignore[attr-defined]
        else:
            delattr(startup.subprocess, "DETACHED_PROCESS")
        if had_group:
            startup.subprocess.CREATE_NEW_PROCESS_GROUP = original_group  # type: ignore[attr-defined]
        else:
            delattr(startup.subprocess, "CREATE_NEW_PROCESS_GROUP")
        if had_frozen:
            startup.sys.frozen = original_frozen  # type: ignore[attr-defined]
        else:
            delattr(startup.sys, "frozen")
        startup.os = original_os  # type: ignore[assignment]

    assert len(captured) == 2, captured
    hidden = captured[0][1]
    visible = captured[1][1]
    assert hidden["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1", hidden
    assert visible["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1", visible
    detached = 0x00000008
    assert int(hidden.get("creationflags", 0)) & detached == detached, hidden
    assert int(visible.get("creationflags", 0)) & detached == 0, visible


def assert_install_marker_forces_folder_and_staff_onboarding() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        intake = root / startup.DESKTOP_INTAKE_FOLDER_NAME
        intake.mkdir()
        marker = root / "onboarding-required.flag"
        marker.write_text("1", encoding="ascii")
        asked: list[str] = []

        class AppStub:
            def __init__(self) -> None:
                self.root = None
                self.preference = True
                self._desktop_intake_enabled_for_session = True
                self.staff_prompts = 0

            def _desktop_intake_preference(self):
                return self.preference

            def _set_desktop_intake_preference(self, enabled):
                self.preference = bool(enabled)
                return True

            def _staff_profile_is_configured(self):
                return True

            def _prompt_staff_profile(self, *, first_run=False):
                assert first_run is True
                self.staff_prompts += 1
                return True

        app = AppStub()
        original_os = app_main.os
        original_marker = app_main._installation_onboarding_marker_path
        original_root = app_main.desktop_intake_root_path
        original_yesno = app_main.messagebox.askyesno
        try:
            app_main.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            app_main._installation_onboarding_marker_path = lambda: marker  # type: ignore[assignment]
            app_main.desktop_intake_root_path = lambda: intake  # type: ignore[assignment]
            app_main.messagebox.askyesno = lambda title, message, **_kwargs: asked.append(message) or True
            app_main._first_launch_onboarding(app)
        finally:
            app_main.messagebox.askyesno = original_yesno
            app_main.desktop_intake_root_path = original_root  # type: ignore[assignment]
            app_main._installation_onboarding_marker_path = original_marker  # type: ignore[assignment]
            app_main.os = original_os  # type: ignore[assignment]

        assert asked == [], "mandatory intake must not ask an opt-out question"
        assert app.staff_prompts == 1, app.staff_prompts
        assert app.preference is True and app._desktop_intake_enabled_for_session is True
        assert not marker.exists(), "completed onboarding marker was not consumed"


def assert_legacy_disabled_preference_heals_and_preserves_user_folder() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        intake = root / startup.DESKTOP_INTAKE_FOLDER_NAME
        intake.mkdir()
        sentinel = intake / "user-file.txt"
        sentinel.write_text("keep", encoding="utf-8")
        marker = root / "no-onboarding-marker.flag"

        class AppStub:
            root = None
            _desktop_intake_enabled_for_session = False

            def __init__(self) -> None:
                self.preference = False

            def _desktop_intake_preference(self):
                return self.preference

            def _set_desktop_intake_preference(self, enabled):
                self.preference = bool(enabled)
                return True

            def _staff_profile_is_configured(self):
                return True

            def _prompt_staff_profile(self, *, first_run=False):
                raise AssertionError("staff prompt must not run without install marker")

        app = AppStub()
        original_os = app_main.os
        original_marker = app_main._installation_onboarding_marker_path
        original_root = app_main.desktop_intake_root_path
        try:
            app_main.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            app_main._installation_onboarding_marker_path = lambda: marker  # type: ignore[assignment]
            app_main.desktop_intake_root_path = lambda: intake  # type: ignore[assignment]
            app_main._first_launch_onboarding(app)
        finally:
            app_main.desktop_intake_root_path = original_root  # type: ignore[assignment]
            app_main._installation_onboarding_marker_path = original_marker  # type: ignore[assignment]
            app_main.os = original_os  # type: ignore[assignment]

        assert app.preference is True
        assert app._desktop_intake_enabled_for_session is True
        assert sentinel.read_text(encoding="utf-8") == "keep"

def main() -> None:
    assert_agent_recreates_deleted_intake_root()
    assert_agent_rebinds_when_desktop_moves()
    assert_gui_poll_rebinds_when_desktop_moves()
    assert_gui_poll_processes_only_new_or_changed_arrivals()
    assert_old_watcher_retires_after_in_place_update()
    assert_gui_launch_handoff_preserves_queued_arrivals()
    assert_agent_suppresses_duplicate_gui_launch_until_heartbeat()
    assert_agent_retries_failed_visible_launch()
    assert_desktop_intake_propagates_rejected_primary()
    assert_unrecognized_word_arrival_gets_one_visible_explanation()
    assert_pyinstaller_children_are_independent_and_gui_is_visible()
    assert_install_marker_forces_folder_and_staff_onboarding()
    assert_legacy_disabled_preference_heals_and_preserves_user_folder()
    print(
        "INTAKE LIFECYCLE REGRESSION OK: self-heal + Desktop rebind + event-driven intake + in-place watcher replacement + queued-arrival handoff + duplicate-launch suppression + failed-launch retry + rejected-primary propagation + visible unrecognized-file feedback + independent PyInstaller child runtime + mandatory install intake"
    )


if __name__ == "__main__":
    main()
