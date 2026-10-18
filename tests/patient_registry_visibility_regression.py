"""Patient registry visibility and small-window UI regression."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from patient_registry import scan_patient_registry
import patient_registry_mixin as prm

def data(fio, admission, discharge=""):
    return SimpleNamespace(fio=fio, admission_date=admission, discharge_date=discharge,
        sick_leave="нет", expert_sick_leave_needed="", expert_sick_leave_from="",
        rvk_referral="нет", rvk_referral_present="", rvk_referral_commissariat="")

def check_registry():
    with TemporaryDirectory(prefix="registry-visibility-") as temp:
        root = Path(temp)
        table = {}
        def add(rel, obj):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            table[path] = obj
        add("Обычный/Обычный первичный.docx", data("Обычный Тест", "01.10.2026"))
        add("Заранее/Заранее первичный.docx", data("Заранее Тест", "05.10.2026"))
        add("Заранее/Заранее Выписной эпикриз.docx", data("", "05.10.2026", "23.10.2026"))
        add("Выписан/Выписан первичный.docx", data("Выписан Тест", "01.09.2026"))
        add("Выписан/Выписан Выписной эпикриз.docx", data("", "01.09.2026", "15.10.2026"))
        add("БезДаты/БезДаты первичный.docx", data("БезДаты Тест", "01.09.2026"))
        add("БезДаты/БезДаты Выписной.docx", data("", "", ""))
        add("Блок/Блок первичный.docx", data("Блок Тест", "02.10.2026"))
        (root / "Блок" / "~$Блок Выписной эпикриз.docx").touch()
        (root / "Блок" / "~$Блок первичный.docx").touch()
        add("Палата 5/Вложенный0/Вложенный0 первичный.docx", data("Вложенный0 Тест", "03.10.2026"))
        add("Палата 5/Вложенный1/Вложенный1 первичный.docx", data("Вложенный1 Тест", "03.10.2026"))
        add("Корневой первичный.docx", data("Корневой Тест", "04.10.2026"))
        add("Будущий/Будущий первичный.docx", data("Будущий Тест", "16.10.2027"))
        def parser(path):
            if path.name.startswith("~$"):
                raise AssertionError("lock file was passed to parser")
            return table[path]
        snapshot = scan_patient_registry(root, as_of=date(2026, 10, 16), parser=parser)
        names = {item.fio for item in snapshot.patients}
        assert names == {"Обычный Тест", "Заранее Тест", "Блок Тест",
                         "Вложенный0 Тест", "Вложенный1 Тест", "Корневой Тест", "БезДаты Тест"}, (names, snapshot.issues)
        assert all(item.folder.name != "Палата 5" for item in snapshot.patients)
        assert any("Выписка не подтверждена" in issue.message and issue.folder.name == "БезДаты Выписной.docx" for issue in snapshot.issues)
        assert all("Выписка не подтверждена" not in issue.message for issue in snapshot.issues if issue.folder.name == "Заранее Выписной эпикриз.docx")
        assert any("16.10.2027" in issue.message and "не показан" in issue.message for issue in snapshot.issues)
        past = scan_patient_registry(root, as_of=date(2026, 10, 10), parser=parser)
        assert "Выписан Тест" in {item.fio for item in past.patients}

def check_ui():
    assert prm.fit_patient_window_to_screen(900, 620, 1920, 1080) == (900, 620, 720, 440)
    w, h, mw, mh = prm.fit_patient_window_to_screen(900, 620, 911, 512)
    assert w <= 887 and h <= 440 and mw <= w and mh <= h
    _, high_dpi_height, _, _ = prm.fit_patient_window_to_screen(900, 620, 1093, 614)
    assert high_dpi_height <= 542
    assert prm._wheel_steps(SimpleNamespace(num=None, delta=-120)) == 1
    assert prm._wheel_steps(SimpleNamespace(num=None, delta=240)) == -2
    assert prm._wheel_steps(SimpleNamespace(num=5, delta=0)) == 1
    assert prm._wheel_steps(SimpleNamespace(num=4, delta=0)) == -1
    source = Path(prm.__file__).read_text(encoding="utf-8")
    body = source[source.index("def show_my_patients("):]
    assert body.index('footer.pack(side="bottom"') < body.index("list_shell.pack(")
    assert "bind_patient_list_wheel(win, canvas)" in body
    assert "fit_patient_window_to_screen(" in body
    assert "bind_label_wrap_to_width(details_label)" in body

if __name__ == "__main__":
    check_registry()
    check_ui()
    print("PATIENT REGISTRY VISIBILITY OK")
