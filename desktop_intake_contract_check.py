"""Headless contract checks for the optional desktop patient-folder workflow."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

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


def main() -> None:
    _assert_naming_contract()
    _assert_primary_detection_contract()
    _assert_top_level_only_and_safe_move()
    print("desktop intake contract: PASS")


if __name__ == "__main__":
    main()
