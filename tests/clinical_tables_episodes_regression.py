"""Real source DOCX and patient-episode audit regressions."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools'))
from docx import Document
from medical_parser import MedicalTextParser
from medical_parser_sanitize import sanitize_diagnosis
from patient_registry import scan_patient_registry
from generation_performance_profile import _make_fixture

def test_table_and_clinical_fields():
    with TemporaryDirectory() as t:
        p=Path(t)/'source.docx';d=Document()
        for k,v in (
            ('История болезни №','К-77'),('Год рождения','1990'),
            ('Зарегистрирован','Нижегородская обл., Борский район'),
            ('Работает в организации','не работает'),
            ('На учёте у психиатров','состоит с 2015 г.'),
            ('Больничный лист','не нужен'),('Оформление инвалидности','нужно'),
        ):
            table=d.add_table(rows=1,cols=2)
            table.cell(0,0).text=k;table.cell(0,1).text=v
        d.add_paragraph('Жалобы: снижение настроения')
        d.add_paragraph('Анамнез: Состояние ухудшилось после смерти мужа')
        d.save(p)
        got=MedicalTextParser().parse_docx(p)
        assert got.case_number=='К-77',got.case_number
        assert got.birth=='1990',got.birth
        assert 'Нижегородская' in got.registered,got.registered
        assert got.work_org in ('','не работает'),got.work_org
        assert got.psych_account.startswith('состоит'),got.psych_account
        assert got.sick_leave=='не нужен',got.sick_leave
        assert got.disability=='нужно',got.disability
        assert 'снижение настроения' in got.complaints
        assert 'смерти мужа' in got.disease_anamnesis
        assert 'смерти мужа' not in got.complaints

def test_name_diagnosis():
    p=MedicalTextParser()
    d=p.parse_text('ФИО: Васильева Ольга Петровна, 1968 г.р.')
    assert d.fio=='Васильева Ольга Петровна',(d.fio,d.birth)
    assert '1968' in d.birth
    d=p.parse_text('Д.р.: 12.05.1980')
    assert d.birth=='12.05.1980',d.birth
    assert sanitize_diagnosis('F32.2 Эпизод\nНаправляется на стационарное лечение в 3 отделение')=='F32.2 Эпизод'

def _record(day):
    return SimpleNamespace(fio='Орлов',admission_date=day,discharge_date='',
        sick_leave='нет',expert_sick_leave_needed='',expert_sick_leave_from='',
        rvk_referral='нет',rvk_referral_present='',rvk_referral_commissariat='')

def test_nested_episode_and_depth():
    with TemporaryDirectory() as t:
        r=Path(t)
        old=r/'Орлов'/'Орлов первичный.docx'
        old.parent.mkdir();old.touch()
        new=r/'Орлов'/'Повторная госпитализация'/'Орлов первичный.docx'
        new.parent.mkdir();new.touch()
        data={old:_record('10.10.2026'),new:_record('15.10.2026')}
        snap=scan_patient_registry(r,as_of=date(2026,10,16),parser=lambda p:data[p])
        assert len(snap.patients)==1
        assert snap.patients[0].primary_path==new
    with TemporaryDirectory() as t:
        r=Path(t);f=r
        for i in range(10):
            f=f/f'уровень{i}';f.mkdir()
        doc=f/'Иванов первичный.docx';doc.touch()
        snap=scan_patient_registry(r,as_of=date(2026,10,16),parser=lambda p:_record('10.10.2026'))
        assert len(snap.patients)==1,(snap.patients,snap.issues)

def test_rvk_conflicts():
    with TemporaryDirectory() as t:
        nav,s,d=_make_fixture(Path(t))
        d.rvk_referral_present='да';d.rvk_referral_commissariat='Борского'
        d.rvk_military_commissariat='Советского'
        try:
            s.create_documents(navigation_path=nav,output_dir=Path(t)/'out',
                selected_docs=['primary','rvk'],override_data=d)
        except ValueError as e:
            assert 'РВК' in str(e)
        else:raise AssertionError('Conflicting RVK regions accepted')

if __name__=='__main__':
    test_table_and_clinical_fields()
    test_name_diagnosis()
    test_nested_episode_and_depth()
    test_rvk_conflicts()
    print('CLINICAL TABLES AND EPISODES: PASS')
