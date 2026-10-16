"""Regression: real patient folder inventory and non-destructive quick document buttons."""
from pathlib import Path
from tempfile import TemporaryDirectory
from patient_registry import patient_document_labels

def main():
    with TemporaryDirectory() as td:
        folder=Path(td)/"Пациент"
        folder.mkdir()
        for name in ("Иванов Первичный осмотр.docx", "Иванов Направление на госпитализацию.docx",
                     "Иванов Дневники.docx", "Иванов Совместный осмотр.docm",
                     "Иванов Акт для РВК.doc", "Иванов Выписной эпикриз.docx",
                     "Иванов Нестандартный документ.docx", "~$Иванов Первичный осмотр.docx"):
            (folder/name).touch()
        labels=patient_document_labels(folder)
        assert labels==(
            "Акт РВК", "Выписной эпикриз", "Дневники",
            "Направление на госпитализацию", "Другой Word",
            "Первичный осмотр", "Совместный осмотр"
        ), labels
        first=folder/"Иванов Первичный осмотр.docx"
        assert patient_document_labels(folder,primary_path=first,single_file=True)==("Первичный осмотр",)
        assert patient_document_labels(folder/"missing")==()
        assert all(f.exists() for f in folder.iterdir()), "inventory must be non-destructive"
    source=(Path(__file__).parents[1]/"patient_registry_mixin.py").read_text(encoding="utf-8")
    for label in ("Выписной эпикриз", "Дневники", "Первичный осмотр"):
        assert f'("{label}",' in source
    assert "self._prepare_registry_quick_document(" in source
    assert "self._load_registry_primary_document(entry, parent=owner_window)" in source
    assert 'self.create_selected_outputs(' not in source[source.index("def _prepare_registry_quick_document("):source.index("def show_my_patients(")]
    print("PATIENT DOCUMENT QUICK ACTIONS OK")

if __name__=="__main__":
    main()
