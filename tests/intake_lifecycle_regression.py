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
        original_scan = startup.desktop_intake_scan_primary_candidates
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
            startup.desktop_intake_scan_primary_candidates = scan  # type: ignore[assignment]
            startup.time.sleep = lambda _seconds: None  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]

            assert startup.run_desktop_intake_agent() == 0
            assert root_path_calls >= 2, root_path_calls
            assert scans == [True, True], scans
            assert root.is_dir(), "watcher did not recreate deleted intake root"
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.time.sleep = original_sleep  # type: ignore[assignment]
            startup.desktop_intake_scan_primary_candidates = original_scan  # type: ignore[assignment]
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
        original_scan = startup.desktop_intake_scan_primary_candidates
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
            startup.desktop_intake_scan_primary_candidates = scan  # type: ignore[assignment]
            startup.time.sleep = lambda _seconds: None  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]

            assert startup.run_desktop_intake_agent() == 0
            assert scans == [first, second], scans
            assert first.is_dir(), "old Desktop intentionally remains present in this regression"
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.time.sleep = original_sleep  # type: ignore[assignment]
            startup.desktop_intake_scan_primary_candidates = original_scan  # type: ignore[assignment]
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

        app = SimpleNamespace(root=RootStub(), _desktop_intake_processing=False)
        original_root_path = startup.desktop_intake_root_path
        original_scan = startup.desktop_intake_scan_primary_candidates
        original_log = startup._desktop_agent_log
        try:
            startup.desktop_intake_root_path = lambda: new_root  # type: ignore[assignment]
            startup.desktop_intake_scan_primary_candidates = (
                lambda root: scanned.append(Path(root)) or []
            )  # type: ignore[assignment]
            startup._desktop_agent_log = lambda _message: None  # type: ignore[assignment]
            startup._desktop_poll_intake(app, old_root)
            assert scanned == [new_root], scanned
        finally:
            startup._desktop_agent_log = original_log  # type: ignore[assignment]
            startup.desktop_intake_scan_primary_candidates = original_scan  # type: ignore[assignment]
            startup.desktop_intake_root_path = original_root_path  # type: ignore[assignment]


def main() -> None:
    assert_agent_recreates_deleted_intake_root()
    assert_agent_rebinds_when_desktop_moves()
    assert_gui_poll_rebinds_when_desktop_moves()
    print("INTAKE LIFECYCLE REGRESSION OK: self-heal + Desktop rebind")


if __name__ == "__main__":
    main()
