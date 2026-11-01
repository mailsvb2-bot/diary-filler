"""Clinician-reported Nov 02 audit: production behaviour, synthetic fixtures."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "tools"))
from docx import Document
from patient_registry import scan_patient_registry, primary_candidates
from diary_batch import _build_text_diary_entries
from diary_service import DynamicEpicrisisInput, build_dynamic_epicrisis_text, dynamic_epicrisis_dates
from medical_formatting import treatment_term_start, treatment_period_text

def stage(root,name):
    path=root/name
    path.parent.mkdir(parents=True,exist_ok=True)
    Document().save(path)
    return path

def rec(fio,adm="01.10.2026",dis=""):
    return SimpleNamespace(fio=fio,admission_date=adm,discharge_date=dis,
      sick_leave="нет",expert_sick_leave_needed="",expert_sick_leave_from="",
      rvk_referral="нет",rvk_referral_present="",rvk_referral_commissariat="")

def test_names_and_service_parents():
    with TemporaryDirectory() as temp:
        root=Path(temp)
        a=stage(root,"Шаблонов Пётр/Шаблонов первичный.docx")
        b=stage(root,"Дневников Иван/Первичные документы/Дневников первичный.docx")
        c=stage(root,"Текстова Анна/ВК/Текстова первичный.docx")
        data={a:rec("Шаблонов Пётр"),b:rec("Дневников Иван"),c:rec("Текстова Анна")}
        snap=scan_patient_registry(root,as_of=date(2026,10,16),parser=lambda p:data[p])
        assert {v.folder.name for v in snap.patients}=={"Шаблонов Пётр","Дневников Иван","Текстова Анна"},snap

def test_namesakes_root():
    with TemporaryDirectory() as temp:
        root=Path(temp)
        a=stage(root,"Иванов Пётр первичный.docx")
        b=stage(root,"Иванов Иван выписной.docx")
        data={a:rec("Иванов Пётр"),b:rec("Иванов Иван",dis="10.10.2026")}
        snap=scan_patient_registry(root,as_of=date(2026,10,16),parser=lambda p:data[p])
        assert len(snap.patients)==1,snap
        assert snap.patients[0].primary_path==a

def test_multiple_sources_and_generated_output():
    with TemporaryDirectory() as temp:
        root=Path(temp)
        a=stage(root,"Петров/Петров первичный.docx")
        b=stage(root,"Петров/Петров первичка повтор.docx")
        generated=stage(root,"Петров/Петров Пётр Первичный осмотр.docx")
        data={a:rec("Петров Пётр"),b:rec("Петров Пётр",adm="10.10.2026")}
        assert generated not in primary_candidates(root/"Петров")
        assert generated not in primary_candidates(root/"Петров")
        snap=scan_patient_registry(root,as_of=date(2026,10,16),parser=lambda p:data[p])
        assert len(snap.patients)==1,snap
        entry=snap.patients[0]
        assert set(entry.primary_choices)=={a,b},entry.primary_choices
        assert "несколько" in entry.warning.casefold()

def test_vks_and_blank_state():
    assert treatment_term_start("27.02.2028","29.02.2028")=="29.02.2028"
    assert treatment_period_text("29.02.2028","29.02.2028").endswith("(1 день)")
    text=build_dynamic_epicrisis_text(DynamicEpicrisisInput(patient_name="Маркер Пациент"))
    assert "Динамическое наблюдение:" in text
    assert "заполнить врачу" in text

def test_empty_diagnosis_service_and_long_horizon():
    from generation_performance_profile import _make_fixture
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        nav,service,data=_make_fixture(root)
        data.diagnosis=""
        data.complaints=""
        created,_=service.create_documents(
            navigation_path=nav,output_dir=root/"out",
            selected_docs=["primary"],override_data=data,
        )
        assert len(created)==1
    # 30 April to early November spans more than twelve ten-day cycles.
    planned=dynamic_epicrisis_dates(date(2026,4,30))
    assert len(planned)>12,len(planned)


def test_joint_exam_next_workday():
    base=[date(2026,5,1),date(2026,5,2),date(2026,5,3),date(2026,5,7)]
    entries,_,_=_build_text_diary_entries(
        ["Пробное клиническое состояние, сохранено без выдумки."],base,
        discharge_date_value=None,force_final_diary=False,
        repeat_statuses=True,patient_gender=None,
    )
    assert any(e.date==date(2026,5,4) and e.is_joint_head_exam for e in entries),entries
    assert not any(e.date==date(2026,5,7) and e.is_joint_head_exam for e in entries),entries

if __name__=="__main__":
    test_names_and_service_parents()
    test_namesakes_root()
    test_multiple_sources_and_generated_output()
    test_vks_and_blank_state()
    test_joint_exam_next_workday()
    test_empty_diagnosis_service_and_long_horizon()
    print("NOV02 AUDIT REGRESSION: PASS")
