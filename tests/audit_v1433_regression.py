"""Audit regressions for patient folders, identity and clinician-selected source."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from patient_registry import scan_patient_registry, _registry_visible_folder
from medical_formatting import treatment_period_text
from medical_models import PatientData
from diary_service import DynamicEpicrisisInput, build_dynamic_epicrisis_text

def record(fio, *, discharge="", admitted="01.10.2026"):
    return SimpleNamespace(
        fio=fio, admission_date=admitted, discharge_date=discharge,
        sick_leave="не нужен", expert_sick_leave_needed="нет",
        expert_sick_leave_from="", rvk_referral="нет",
        rvk_referral_present="нет", rvk_referral_commissariat=""
    )

def test_names_and_root_discharge():
    with TemporaryDirectory() as t:
        root=Path(t)
        assert _registry_visible_folder(root/"Шаблонов Пётр")
        assert _registry_visible_folder(root/"Дневников Иван")
        assert not _registry_visible_folder(root/"Шаблоны дневников")
        d={}
        for name in ("Шаблонов Пётр","Дневников Иван"):
            folder=root/name
            folder.mkdir()
            doc=folder/(name+" первичный.docx")
            doc.touch()
            d[doc]=record(name)
        primary=root/"Иванов Пётр первичный.docx"
        primary.touch()
        discharged=root/"Иванов Иван выписной.docx"
        discharged.touch()
        d[primary]=record("Иванов Пётр")
        d[discharged]=record("Иванов Иван",discharge="01.10.2026")
        snapshot=scan_patient_registry(root,as_of=date(2026,10,2),parser=lambda path:d[path])
        names={patient.fio for patient in snapshot.patients}
        assert {"Шаблонов Пётр","Дневников Иван","Иванов Пётр"} <= names,names

def test_no_fabricated_observation():
    text=build_dynamic_epicrisis_text(DynamicEpicrisisInput(patient_name="Маркер Тестовый",clinical_state=""))
    assert "Динамическое наблюдение:" in text
    assert "требуется заполнение врачом" in text
    assert treatment_period_text("29.02.2028","29.02.2028").endswith("(1 день)")

def test_joint_exam_first_working_day():
    from diary_batch import _build_text_diary_entries
    entries, _final, _gender = _build_text_diary_entries(
        ["Состояние осмотрено."],
        [date(2026, 5, 1), date(2026, 5, 2),
         date(2026, 5, 3), date(2026, 5, 7)],
        discharge_date_value=date(2026, 5, 25),
        force_final_diary=False,
        repeat_statuses=True, patient_gender=None,
    )
    joint = [item for item in entries if item.is_joint_head_exam]
    assert joint[0].date == date(2026, 5, 4), joint
    assert "требуется заполнение врачом" in joint[0].text


def test_machine_generated_primary_is_not_source():
    from docx import Document
    from patient_registry import primary_candidates
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from generation_performance_profile import _make_fixture
    with TemporaryDirectory() as t:
        folder = Path(t)
        intake = folder / "Маркер Тестовый первичный.docx"
        Document().save(intake)
        assert primary_candidates(folder) == [intake]
        nav, service, data = _make_fixture(folder)
        output_files, _ = service.create_documents(
            navigation_path=nav, output_dir=folder,
            selected_docs=["primary"], override_data=data,
        )
        assert len(output_files) == 1
        assert "diary-filler:generated-primary" in Document(
            str(output_files[0])
        ).core_properties.keywords
        assert primary_candidates(folder) == [intake]


def test_empty_diagnosis_is_clinician_decision():
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from generation_performance_profile import _make_fixture
    with TemporaryDirectory() as t:
        nav, service, data = _make_fixture(Path(t))
        data.diagnosis = ""
        data.complaints = ""
        generated, _ = service.create_documents(
            navigation_path=nav, output_dir=Path(t)/"out",
            selected_docs=["primary"], override_data=data,
        )
        assert len(generated) == 1


def test_vk_sick_leave_start_and_long_horizon():
    from medical_formatting import treatment_period_text, treatment_term_start
    from diary_service import dynamic_epicrisis_dates
    assert treatment_term_start("27.02.2028", "29.02.2028") == "29.02.2028"
    assert treatment_period_text(
        treatment_term_start("27.02.2028", "29.02.2028"), "29.02.2028"
    ).endswith("(1 день)")
    # Explicitly scoped multi-month runs must not be truncated at 12.
    dates = dynamic_epicrisis_dates(
        date(2025,1,1), discharge_date=date(2026,1,2), limit=100
    )
    assert len(dates) > 12


def test_vk_explicit_admission_vs_sick_leave_date():
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from generation_performance_profile import _make_fixture
    from medical_docx_reader import extract_docx_text
    with TemporaryDirectory() as t:
        nav, service, data = _make_fixture(Path(t))
        data.admission_date = "10.06.2026"
        data.expert_sick_leave_from = "15.06.2026"
        data.sick_leave = "нужен с 15.06.2026"
        data.sick_leave_vk_commission_date = "17.06.2026"
        docs, _ = service.create_documents(
            navigation_path=nav, output_dir=Path(t)/"vk",
            selected_docs=["sick_leave_vk"], override_data=data,
        )
        text = extract_docx_text(docs[0])
        assert "Находится на лечении с 15.06.2026 (3 дня)" in text
        assert "Дата госпитализации: 10.06.2026" in text
        parsed = service.parse_primary_document(docs[0])
        assert parsed.admission_date == "10.06.2026", parsed.admission_date


if __name__=="__main__":
    test_names_and_root_discharge()
    test_no_fabricated_observation()
    test_joint_exam_first_working_day()
    test_machine_generated_primary_is_not_source()
    test_empty_diagnosis_is_clinician_decision()
    test_vk_sick_leave_start_and_long_horizon()
    test_vk_explicit_admission_vs_sick_leave_date()
    print("AUDIT V1433 REGRESSIONS: PASS")
