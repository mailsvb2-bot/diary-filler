"""Inventory classification, compact actions and tray cleanup regression."""
from pathlib import Path
from tempfile import TemporaryDirectory
import patient_registry
def main():
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        for filename in ("Иванов Первичный осмотр.docx","Иванов Направление на госпитализацию.docx",
                         "Иванов Осмотр врача приёмного покоя.docx","Иванов Этапный эпикриз.docx",
                         "Иванов Выписной эпикриз.docx","Иванов ВК на МСЭ.docx",
                         "Иванов Акт РВК.docx","~$Иванов Дневники.docx"):
            (root/filename).touch()
        got=patient_registry.patient_document_labels(root)
        for expected in ("Первичный осмотр","Направление на госпитализацию","Осмотр приёмного покоя","Другой эпикриз","Выписной эпикриз","ВК на МСЭ","Акт РВК"):
            assert expected in got,(expected,got)
        assert "Дневники" not in got,got
        single=patient_registry.patient_document_labels(root,primary_path=root/"Иванов Первичный осмотр.docx",single_file=True)
        assert single==("Первичный осмотр",),single
    s=(Path(__file__).resolve().parents[1]/"patient_registry_mixin.py").read_text(encoding="utf-8")
    assert 'win.bind("<Destroy>", stop_tray_on_destroy' in s
    assert 'quick.grid(row=3, column=0, columnspan=2' in s
    assert "bind_label_wrap_to_width(documents_label)" in s
    assert "bind_label_wrap_to_width(hint_label)" in s
    for label in ("Выписной эпикриз","Дневники","Первичный осмотр"):
        assert f'("{label}",' in s
    print("PATIENT INVENTORY AND LAYOUT OK")
if __name__=="__main__":main()
