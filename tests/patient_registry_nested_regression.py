"""Patient registry: six independent DOCX-backed nested-folder regressions."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from docx import Document
from patient_registry import scan_patient_registry

AS_OF = date(2026, 10, 16)

def record(fio, discharge=""):
    return SimpleNamespace(
        fio=fio, admission_date="01.10.2026", discharge_date=discharge,
        sick_leave="нет", expert_sick_leave_needed="", expert_sick_leave_from="",
        rvk_referral_present="", rvk_referral="нет", rvk_referral_commissariat="",
    )

def stage(root, name, fio, discharge=""):
    f=root/name
    f.parent.mkdir(parents=True, exist_ok=True)
    doc=Document()
    doc.add_paragraph(f"Ф.И.О.: {fio}")
    doc.add_paragraph("Дата поступления: 01.10.2026")
    if discharge:doc.add_paragraph(f"Дата выписки: {discharge}")
    doc.save(f)
    return f, record(fio, discharge)

def scan(root, entries):
    return scan_patient_registry(root, as_of=AS_OF, parser=lambda path: entries[path])

def test_ward_with_schedule():
    with TemporaryDirectory() as t:
        root=Path(t)
        entries=dict([
            stage(root, "Палата 1/Иванов/Иванов первичный.docx", "Иванов"),
            stage(root, "Палата 1/Петров/Петров первичный.docx", "Петров"),
            stage(root, "Палата 1/График дежурств.docx", "СЛУЖЕБНЫЙ"),
        ])
        s=scan(root,entries)
        assert {p.fio for p in s.patients}=={"Иванов","Петров"}

def test_service_folders():
    with TemporaryDirectory() as t:
        root=Path(t)
        entries=dict([
            stage(root, "шаблоны дневников/Образец.docx", "СЛУЖЕБНЫЙ"),
            stage(root, "тексты дневников/Первичка.docx", "СЛУЖЕБНЫЙ"),
            stage(root, "Иванов/Иванов первичный.docx", "Иванов"),
        ])
        assert {p.fio for p in scan(root,entries).patients}=={"Иванов"}

def test_patient_document_subfolders():
    with TemporaryDirectory() as t:
        root=Path(t)
        entries=dict([
            stage(root, "Сидоров/Первичка/Сидоров первичный.docx", "Сидоров"),
            stage(root, "Сидоров/Дневники/01.docx", "СЛУЖЕБНЫЙ"),
        ])
        snap=scan(root,entries)
        assert [(p.fio,p.folder.name) for p in snap.patients]==[("Сидоров","Сидоров")]

def test_empty_and_non_word_not_counted():
    with TemporaryDirectory() as t:
        root=Path(t)
        (root/"Пустая").mkdir()
        (root/"Сканы").mkdir()
        (root/"Сканы"/"паспорт.pdf").touch()
        snap=scan(root,{})
        assert not snap.patients
        assert any("Пустая" in str(i.folder) for i in snap.issues)

def test_only_hidden_subfolder():
    with TemporaryDirectory() as t:
        root=Path(t)
        (root/"Скрытая"/".tmp").mkdir(parents=True)
        snap=scan(root,{})
        assert not snap.patients
        assert any(i.folder.name=="Скрытая" for i in snap.issues)

def test_root_discharge():
    with TemporaryDirectory() as t:
        root=Path(t)
        entries=dict([
            stage(root,"Лебедев первичный.docx","Лебедев"),
            stage(root,"Лебедев Выписной эпикриз.docx","Лебедев","10.10.2026"),
        ])
        assert "Лебедев" not in {p.fio for p in scan(root,entries).patients}
        old=scan_patient_registry(root, as_of=date(2026,10,5),parser=lambda p:entries[p])
        assert "Лебедев" in {p.fio for p in old.patients}

if __name__=="__main__":
    test_ward_with_schedule()
    test_service_folders()
    test_patient_document_subfolders()
    test_empty_and_non_word_not_counted()
    test_only_hidden_subfolder()
    test_root_discharge()
    print("PATIENT REGISTRY SIX CASES: PASS")
