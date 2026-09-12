"""Headless contract checks for the optional desktop patient-folder workflow."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import desktop_intake_agent as agent
from desktop_intake import (
    is_candidate_word_file,
    iter_candidate_files,
    prepare_patient_work_folder,
    primary_document_score,
)
from desktop_patient_folder import build_patient_folder_name


def _assert_naming_contract() -> None:
    name = build_patient_folder_name(
        fio="Иванов Иван Иванович",
        admission_date=date(2026, 5, 12),
        fallback_stem="Первичный осмотр",
    )
    assert name == "Иванов И.И. май 2026", name

    custom = build_patient_folder_name(
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
    assert primary_document_score(primary) >= 5
    assert primary_document_score(referral) >= 5
    assert primary_document_score(discharge) < 0
    assert is_candidate_word_file("Первичный.docx")
    assert is_candidate_word_file("Первичный.docm")
    assert not is_candidate_word_file("~$Первичный.docx")
    assert not is_candidate_word_file("ЭПИ.pdf")


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

        candidates = tuple(iter_candidate_files(root))
        assert candidates == (top,), candidates

        moved = prepare_patient_work_folder(
            top,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert moved.parent.name == "Иванов И.И. май 2026"
        assert moved.read_bytes() == b"same-primary"
        assert not top.exists()

        duplicate = root / "Первичный.docx"
        duplicate.write_bytes(b"same-primary")
        reused = prepare_patient_work_folder(
            duplicate,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert reused == moved
        assert not duplicate.exists()

        changed = root / "Первичный исправленный.docx"
        changed.write_bytes(b"changed-primary")
        second = prepare_patient_work_folder(
            changed,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert second.parent.name == "Иванов И.И. май 2026 (2)"
        assert second.read_bytes() == b"changed-primary"


def _assert_agent_update_and_encoding_contract() -> None:
    payload = agent._startup_vbs_payload([r"C:\Программа\MedicalDiaryAutofill.exe", agent.AGENT_ARGUMENT])
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

        original_runtime_dir = agent._local_runtime_dir
        original_native_command = agent._native_gui_command
        try:
            agent._local_runtime_dir = lambda: runtime  # type: ignore[assignment]
            agent._native_gui_command = lambda: [str(current)]  # type: ignore[assignment]
            agent._write_agent_handoff()
            assert agent._agent_is_retired() is False
            assert agent._launch_command() == [str(current)]

            # Simulate yesterday's already-running agent after today's EXE has
            # published ownership.  It must retire instead of launching itself.
            agent._native_gui_command = lambda: [str(old)]  # type: ignore[assignment]
            assert agent._agent_is_retired() is True
            assert agent._launch_command() == [str(current)]
        finally:
            agent._local_runtime_dir = original_runtime_dir  # type: ignore[assignment]
            agent._native_gui_command = original_native_command  # type: ignore[assignment]


def main() -> None:
    _assert_naming_contract()
    _assert_primary_detection_contract()
    _assert_top_level_only_and_safe_move()
    _assert_agent_update_and_encoding_contract()
    print("desktop intake contract: PASS")


if __name__ == "__main__":
    main()
