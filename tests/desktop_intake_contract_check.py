"""Headless contract checks for the optional desktop patient-folder workflow."""
from __future__ import annotations

import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main as app_main
import startup


def _assert_naming_contract() -> None:
    name = startup.desktop_build_patient_folder_name(
        fio="Иванов Иван Иванович",
        admission_date=date(2026, 5, 12),
        fallback_stem="Первичный осмотр",
    )
    assert name == "Иванов И.И. май 2026", name

    custom = startup.desktop_build_patient_folder_name(
        fio="Петров Пётр Петрович",
        admission_date="03.09.2026",
        discharge_date="19.09.2026",
        fallback_stem="patient",
        settings={"parts": ["full_fio", "admission_discharge_dates"], "date_format": "short"},
    )
    assert custom == "Петров Пётр Петрович 03.09.26 — 19.09.26", custom


def _assert_primary_detection_contract() -> None:
    primary = """
    12.05.2026 Первичный осмотр
    История болезни № 123
    Ф.И.О. Иванов Иван Иванович
    Жалобы при поступлении
    Психический статус
    Диагноз
    План лечения
    """
    referral = """
    12.05.2026 Направление на госпитализацию
    ФИО Иванов Иван Иванович
    Диагноз F20.0
    """
    discharge = """
    Выписной эпикриз
    История болезни № 123
    Ф.И.О. Иванов Иван Иванович
    Диагноз F20.0
    Лечение
    """
    assert startup.desktop_intake_primary_score(primary) >= 5
    assert startup.desktop_intake_primary_score(referral) >= 5
    assert startup.desktop_intake_primary_score(discharge) < 0
    assert startup.desktop_intake_is_candidate_word_file("Первичный.docx")
    assert startup.desktop_intake_is_candidate_word_file("Первичный.docm")
    assert not startup.desktop_intake_is_candidate_word_file("~$Первичный.docx")
    assert not startup.desktop_intake_is_candidate_word_file("ЭПИ.pdf")


def _assert_canonical_primary_parser_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical = root / "patient.docx"
        doc = Document()
        doc.add_paragraph("12.05.2026")
        doc.add_paragraph("Ф.И.О.: Иванов Иван Иванович")
        doc.add_paragraph("Дата рождения: 01.01.1980")
        doc.add_paragraph("В 3 отделение КДП поступает первично")
        doc.add_paragraph("Анамнез жизни: без особенностей")
        doc.add_paragraph("Психический статус: контактен")
        doc.add_paragraph("Диагноз: F20.0")
        doc.save(canonical)
        assert startup.desktop_intake_is_primary_document(canonical), "canonical parser primary was rejected"

        discharge = root / "discharge.docx"
        doc = Document()
        doc.add_paragraph("Выписной эпикриз")
        doc.add_paragraph("Ф.И.О.: Иванов Иван Иванович")
        doc.add_paragraph("Дата рождения: 01.01.1980")
        doc.add_paragraph("Диагноз: F20.0")
        doc.add_paragraph("Лечение: терапия")
        doc.save(discharge)
        assert not startup.desktop_intake_is_primary_document(discharge), "discharge must stay excluded"


def _assert_onboarding_repairs_missing_intake_root() -> None:
    """A stale false setting must not permanently suppress the normal intake folder."""

    class AppStub:
        def __init__(self) -> None:
            self.root = None
            self.preference = False
            self._desktop_intake_enabled_for_session = False

        def _desktop_intake_preference(self) -> bool:
            return self.preference

        def _set_desktop_intake_preference(self, enabled: bool) -> None:
            self.preference = bool(enabled)

        def _staff_profile_is_configured(self) -> bool:
            return True

    with tempfile.TemporaryDirectory() as tmp:
        intake_root = Path(tmp) / startup.DESKTOP_INTAKE_FOLDER_NAME
        original_os = app_main.os
        original_resolver = app_main.desktop_intake_root_path
        try:
            app_main.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            app_main.desktop_intake_root_path = lambda: intake_root  # type: ignore[assignment]
            app = AppStub()
            app_main._first_launch_onboarding(app)
            assert intake_root.is_dir(), "normal Windows onboarding did not recreate intake root"
            assert app._desktop_intake_enabled_for_session is True
            assert app.preference is True, "legacy false intake preference was not healed"
        finally:
            app_main.desktop_intake_root_path = original_resolver  # type: ignore[assignment]
            app_main.os = original_os  # type: ignore[assignment]


def _assert_agent_heartbeat_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        original_runtime_dir = startup._desktop_runtime_dir
        try:
            startup._desktop_runtime_dir = lambda: runtime  # type: ignore[assignment]
            assert startup._desktop_agent_is_active() is False
            startup._desktop_touch_agent_heartbeat()
            assert startup._desktop_agent_is_active() is True
            heartbeat = runtime / "desktop-intake-agent.heartbeat"
            heartbeat.write_text(
                '{"schema": 1, "timestamp": %s, "identity": "%s"}'
                % (time.time() - 60, startup._desktop_current_agent_identity()),
                encoding="ascii",
            )
            assert startup._desktop_agent_is_active() is False
        finally:
            startup._desktop_runtime_dir = original_runtime_dir  # type: ignore[assignment]


def _assert_top_level_only_and_safe_move() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "Выписанные пациенты"
        root.mkdir()
        nested = root / "Старый пациент"
        nested.mkdir()
        (nested / "Первичный.docx").write_bytes(b"nested")
        top = root / "Первичный.docx"
        top.write_bytes(b"same-primary")

        candidates = startup.desktop_intake_iter_candidates(root)
        assert candidates == (top,), candidates

        moved = startup.desktop_intake_prepare_patient_folder(
            top,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert moved.parent.name == "Иванов И.И. май 2026"
        assert moved.read_bytes() == b"same-primary"
        assert not top.exists()

        duplicate = root / "Первичный.docx"
        duplicate.write_bytes(b"same-primary")
        reused = startup.desktop_intake_prepare_patient_folder(
            duplicate,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert reused == moved
        assert not duplicate.exists()

        changed = root / "Первичный исправленный.docx"
        changed.write_bytes(b"changed-primary")
        second = startup.desktop_intake_prepare_patient_folder(
            changed,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert second.parent.name == "Иванов И.И. май 2026 (2)"
        assert second.read_bytes() == b"changed-primary"


def _assert_agent_update_and_encoding_contract() -> None:
    payload = startup.desktop_intake_startup_vbs_payload(
        [r"C:\Программа\MedicalDiaryAutofill.exe", startup.DESKTOP_INTAKE_AGENT_ARGUMENT]
    )
    encoded = payload.encode("utf-16")
    assert encoded.startswith(b"\xff\xfe")
    assert not encoded.startswith(b"\xef\xbb\xbf")
    assert payload.splitlines()[0] == "On Error Resume Next"
    assert "WScript.Shell" in payload
    assert "shell.Run" in payload

    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        current = runtime / "new" / "MedicalDiaryAutofill.exe"
        current.parent.mkdir()
        current.write_bytes(b"stub")
        old = runtime / "old" / "MedicalDiaryAutofill.exe"
        old.parent.mkdir()
        old.write_bytes(b"stub")

        original_runtime_dir = startup._desktop_runtime_dir
        original_native_command = startup._desktop_native_gui_command
        try:
            startup._desktop_runtime_dir = lambda: runtime  # type: ignore[assignment]
            startup._desktop_native_gui_command = lambda: [str(current)]  # type: ignore[assignment]
            startup._desktop_write_agent_handoff()
            assert startup._desktop_agent_is_retired() is False
            assert startup._desktop_launch_command() == [str(current)]

            startup._desktop_native_gui_command = lambda: [str(old)]  # type: ignore[assignment]
            assert startup._desktop_agent_is_retired() is True
            assert startup._desktop_launch_command() == [str(current)]
        finally:
            startup._desktop_runtime_dir = original_runtime_dir  # type: ignore[assignment]
            startup._desktop_native_gui_command = original_native_command  # type: ignore[assignment]


def main() -> None:
    _assert_naming_contract()
    _assert_primary_detection_contract()
    _assert_canonical_primary_parser_contract()
    _assert_onboarding_repairs_missing_intake_root()
    _assert_top_level_only_and_safe_move()
    _assert_agent_update_and_encoding_contract()
    _assert_agent_heartbeat_contract()
    print("desktop intake contract: PASS")


if __name__ == "__main__":
    main()
