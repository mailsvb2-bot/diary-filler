"""Selective Nov 04 main-aligned audit: document provenance and diary safety."""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docx import Document

from diary_batch import _build_text_diary_entries, _text_diary_dates_from_sources
from patient_registry import primary_candidates, patient_source_candidates


def test_renamed_generated_primary_is_not_a_new_source():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        generated = root / "Иванов первичный.docx"
        doc = Document()
        doc.core_properties.keywords = "diary-filler:generated-primary"
        doc.save(generated)
        assert generated not in primary_candidates(root)
        assert generated not in patient_source_candidates(root)
        real = root / "Петров первичный.docx"
        Document().save(real)
        assert real in primary_candidates(root)


def test_generated_primary_has_provenance_metadata():
    from medical_service import MedicalDocumentService
    from medical_models import PatientData
    from tools.generation_performance_profile import _make_fixture
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        nav, service, data = _make_fixture(root)
        generated, _ = service.create_documents(
            navigation_path=nav, output_dir=root / "out",
            selected_docs=["primary"], override_data=data
        )
        assert generated and "diary-filler:generated-primary" in (
            Document(str(generated[0])).core_properties.keywords or ""
        )


def test_shifted_joint_exam_requires_real_physician_note():
    entries, _, _ = _build_text_diary_entries(
        ["Оригинальная запись относится только к исходной дате."],
        [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3), date(2026, 5, 7)],
        discharge_date_value=None, force_final_diary=False,
        repeat_statuses=True, patient_gender=None,
    )
    shifted = [e for e in entries if e.date == date(2026, 5, 4)]
    assert len(shifted) == 1 and shifted[0].is_joint_head_exam
    assert "заполнить врачу" in shifted[0].text
    assert "Оригинальная запись" not in shifted[0].text


def test_no_future_diaries_when_discharge_unknown():
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "Даты.docx"
        doc = Document()
        doc.add_paragraph((date.today() - timedelta(days=1)).strftime("%d.%m.%Y"))
        doc.save(source)
        dates = _text_diary_dates_from_sources(
            [source], admission_date_value=date.today()-timedelta(days=2),
            discharge_date_value=None,
        )
        assert all(day <= date.today() for day in dates)
