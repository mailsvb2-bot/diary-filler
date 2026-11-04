"""PR #367 follow-ups: provenance rejections in nested patient-document
subfolders are surfaced once, and the release-gate runner guard works."""
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
from patient_registry import GENERATED_SOURCE_REJECTED_MESSAGE, scan_patient_registry


def _generated(path: Path) -> None:
    doc = Document()
    doc.core_properties.keywords = "diary-filler:generated-primary"
    doc.save(path)


def _parse(path):
    return SimpleNamespace(
        fio="Маркер Тестовый Пациент", admission_date="01.10.2026", discharge_date="",
        sick_leave="нет", expert_sick_leave_needed="нет", rvk_referral="нет",
    )


def test_nested_subfolder_rejection_is_reported_once():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        patient = root / "Петров"
        docs = patient / "Первичка"
        deep = docs / "Архив"
        deep.mkdir(parents=True)
        real = docs / "Петров первичный.docx"
        Document().save(real)
        nested = docs / "Копия первичный.docx"
        deeper = deep / "Старый первичный.docx"
        _generated(nested)
        _generated(deeper)
        snapshot = scan_patient_registry(root, as_of=date(2026, 10, 10), parser=_parse)
        assert [p.primary_path for p in snapshot.patients] == [real], snapshot.patients
        flagged = [i.folder for i in snapshot.issues if i.message == GENERATED_SOURCE_REJECTED_MESSAGE]
        assert sorted(flagged) == sorted([nested, deeper]), snapshot.issues
        assert len(flagged) == len(set(flagged))


def test_nested_rejection_uses_cheap_filters_first():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        docs = root / "Петров" / "Документы"
        docs.mkdir(parents=True)
        Document().save(docs / "Петров первичный.docx")
        _generated(docs / "Анализы крови.docx")
        _generated(docs / "Маркер Тестовый Третий Первичный осмотр.docx")
        opened = []
        real_check = patient_registry._has_generated_primary_provenance

        def spy(path):
            opened.append(Path(path).name)
            return real_check(path)

        with mock.patch.object(patient_registry, "_has_generated_primary_provenance", spy):
            snapshot = scan_patient_registry(root, as_of=date(2026, 10, 10), parser=_parse)
        assert "Анализы крови.docx" not in opened, opened
        assert "Маркер Тестовый Третий Первичный осмотр.docx" not in opened, opened
        assert not any(i.message == GENERATED_SOURCE_REJECTED_MESSAGE for i in snapshot.issues)


def test_release_check_scripts_have_runners():
    sys.path.insert(0, str(ROOT / "tools"))
    from script_runner_guard import find_noop_scripts
    assert find_noop_scripts(ROOT) == []


def test_runner_guard_detects_missing_runner():
    from tools.script_runner_guard import script_problems
    with TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.py"
        bad.write_text("def test_a():\n    assert False\n", encoding="utf-8")
        assert script_problems(bad)
        partial = Path(tmp) / "partial.py"
        partial.write_text(
            "def test_a():\n    pass\n\ndef test_b():\n    pass\n\n"
            "if __name__ == '__main__':\n    test_a()\n", encoding="utf-8")
        assert any("test_b" in p for p in script_problems(partial))
        good = Path(tmp) / "good.py"
        good.write_text(
            "def test_a():\n    pass\n\nif __name__ == '__main__':\n"
            "    for name, fn in sorted(globals().items()):\n"
            "        if name.startswith('test_') and callable(fn):\n            fn()\n",
            encoding="utf-8")
        assert script_problems(good) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("PR367 FOLLOW-UP REGRESSION: PASS")
