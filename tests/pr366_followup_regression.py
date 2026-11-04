"""PR #366 follow-ups: diary template for shifted joint exams, cheap-first
provenance filtering and visible provenance rejections in the registry."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docx import Document

import patient_registry
from diary_batch import _build_text_diary_entries
from diary_constants import DYNAMIC_OBSERVATION_TEMPLATE
from patient_registry import (
    GENERATED_SOURCE_REJECTED_MESSAGE,
    patient_source_candidates,
    primary_candidates,
    scan_patient_registry,
)


def _generated(path: Path) -> Path:
    doc = Document()
    doc.core_properties.keywords = "diary-filler:generated-primary"
    doc.save(path)
    return path


def test_shifted_joint_exam_uses_project_dynamic_template():
    entries, _, _ = _build_text_diary_entries(
        ["Оригинальная запись относится только к исходной дате."],
        [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3), date(2026, 5, 7)],
        discharge_date_value=None, force_final_diary=False,
        repeat_statuses=True, patient_gender=None,
    )
    shifted = [e for e in entries if e.date == date(2026, 5, 4)]
    assert len(shifted) == 1 and shifted[0].is_joint_head_exam
    assert shifted[0].text == DYNAMIC_OBSERVATION_TEMPLATE, shifted[0].text
    assert "Данные осмотра отсутствуют" not in shifted[0].text
    assert all("Оригинальная запись" not in e.text for e in entries if e.date == date(2026, 5, 4))


def test_provenance_check_runs_only_after_name_filters():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        Document().save(root / "Иванов первичный.docx")
        Document().save(root / "~$Иванов первичный.docx")
        Document().save(root / "Маркер Тестовый Третий Первичный осмотр.docx")
        Document().save(root / "Расписание.docx")
        Document().save(root / "Иванов выписной.docx")
        (root / "notes.txt").write_text("x", encoding="utf-8")
        seen: list[str] = []
        real = patient_registry._has_generated_primary_provenance

        def spy(path):
            seen.append(path.name)
            return real(path)

        with mock.patch.object(patient_registry, "_has_generated_primary_provenance", spy):
            assert [p.name for p in primary_candidates(root)] == ["Иванов первичный.docx"]
        assert seen == ["Иванов первичный.docx"], seen

        (root / "Иванов первичный.docx").unlink()
        seen.clear()
        with mock.patch.object(patient_registry, "_has_generated_primary_provenance", spy):
            assert [p.name for p in patient_source_candidates(root)] == ["Расписание.docx"]
        assert sorted(seen) == ["Расписание.docx"], seen


def test_provenance_rejection_is_reported_not_silent():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "Петров"
        folder.mkdir()
        rejected = _generated(folder / "Петров первичный.docx")
        real = folder / "Петров исходный первичный.docx"
        Document().save(real)
        root_rejected = _generated(root / "Сидоров первичный.docx")

        def parse(path):
            return SimpleNamespace(
                fio="Петров Петр", admission_date="01.10.2026", discharge_date="",
                sick_leave="нет", expert_sick_leave_needed="нет", rvk_referral="нет",
            )

        snapshot = scan_patient_registry(root, as_of=date(2026, 10, 10), parser=parse)
        assert [p.primary_path for p in snapshot.patients] == [real]
        flagged = {i.folder for i in snapshot.issues if i.message == GENERATED_SOURCE_REJECTED_MESSAGE}
        assert flagged == {rejected, root_rejected}, snapshot.issues
        assert GENERATED_SOURCE_REJECTED_MESSAGE.startswith("Файл создан программой")


def test_plain_sources_produce_no_provenance_issue():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "Петров"
        folder.mkdir()
        Document().save(folder / "Петров первичный.docx")
        parse = lambda path: SimpleNamespace(
            fio="Петров Петр", admission_date="01.10.2026", discharge_date="",
            sick_leave="нет", expert_sick_leave_needed="нет", rvk_referral="нет",
        )
        snapshot = scan_patient_registry(root, as_of=date(2026, 10, 10), parser=parse)
        assert not any(i.message == GENERATED_SOURCE_REJECTED_MESSAGE for i in snapshot.issues)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
