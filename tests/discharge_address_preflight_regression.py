"""End-to-end address fidelity and physician missing-field preflight."""
from __future__ import annotations
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from medical_service import MedicalDocumentService
from medical_docx_reader import extract_docx_text
from actions_creation_orchestrator import ActionsCreationOrchestratorMixin
from medical_models import PatientData

def main():
    service = MedicalDocumentService()
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "primary.docx"
        source_doc = Document()
        for line in (
            "10.06.2026 Первичный осмотр",
            "Ф.И.О.: Маркер Адресов Тестовый",
            "Год рождения: 1980",
            "Регистрация по адресу: г. Нижний Новгород, ул. Макетная, д. 42",
            "История болезни № 123",
            "Диагноз: F32.1",
            "Лечение: тестовое назначение врача",
        ):
            source_doc.add_paragraph(line)
        source_doc.save(source)
        parsed = service.parse_primary_document(source)
        assert parsed.registered == "г. Нижний Новгород, ул. Макетная, д. 42", parsed.registered
        parsed.admission_date = "10.06.2026"
        parsed.discharge_date = "20.06.2026"
        parsed.case_number = "123"
        parsed.diagnosis = "F32.1"
        parsed.treatment_plan = "тестовое назначение врача"
        output, _ = service.create_documents(
            navigation_path=source,
            output_dir=Path(tmp) / "output",
            selected_docs=["discharge"],
            override_data=parsed,
        )
        result = extract_docx_text(output[0])
        assert "г. Нижний Новгород, ул. Макетная, д. 42" in result, result

    host = SimpleNamespace(root=None)
    method = ActionsCreationOrchestratorMixin._resolve_unrecognized_generation_fields
    missing = PatientData(registered="", complaints="")
    with patch("actions_creation_orchestrator.simpledialog.askstring", return_value="г. Тест, д. 1"), patch(
        "actions_creation_orchestrator.messagebox.askyesnocancel", return_value=False
    ):
        assert method(host, missing, ["discharge"]) is True
        assert missing.registered == "г. Тест, д. 1"
    empty = PatientData(registered="")
    with patch("actions_creation_orchestrator.simpledialog.askstring", return_value=None):
        assert method(host, empty, ["discharge"]) is False
    assert empty.registered == ""
    print("DISCHARGE ADDRESS FIDELITY AND POPUP PREFLIGHT OK")

if __name__ == "__main__":
    main()
