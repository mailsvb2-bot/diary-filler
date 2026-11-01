"""Test real physician-facing paths without launching a Tk mainloop."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from actions_creation_orchestrator import ActionsCreationOrchestratorMixin
from patient_registry_mixin import PatientRegistryMixin
from medical_models import PatientData
from patient_registry import PatientRegistryEntry

def test_missing_address_across_selected_documents():
    for selected in (["primary"],["sick_leave_vk"],["vk_mse"],["rvk"],["discharge"]):
        data=PatientData(registered="")
        host=SimpleNamespace(root=None,_missing_clinical_fields_for_popup=lambda data: [])
        with patch("actions_creation_orchestrator.simpledialog.askstring",return_value="ул. Макетная, 5") as ask:
            assert ActionsCreationOrchestratorMixin._resolve_unrecognized_generation_fields(host,data,selected)
            assert data.registered=="ул. Макетная, 5"
            assert ask.call_count==1

def test_missing_section_no_and_empty_yes():
    host=SimpleNamespace(root=None,_missing_clinical_fields_for_popup=lambda data:[("diagnosis","Диагноз")])
    for answer in (False,True):
        data=PatientData(diagnosis="", registered="Адрес тестового пациента")
        with patch("actions_creation_orchestrator.messagebox.askyesnocancel",return_value=answer) as ask:
            with patch("actions_creation_orchestrator.simpledialog.askstring",return_value=""):
                assert ActionsCreationOrchestratorMixin._resolve_unrecognized_generation_fields(host,data,["primary"])
                assert data.diagnosis==""
                assert ask.call_args.kwargs["default"]=="no"

def test_choose_source_on_open():
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        a=root/"Маркер первичный.docx";a.touch()
        b=root/"Маркер повторный первичный.docx";b.touch()
        entry=PatientRegistryEntry(
            fio="Маркер Пациент",folder=root,primary_path=a,admission_date=None,
            sick_leave_needed=False,sick_leave_from=None,primary_choices=(a,b)
        )
        chosen=[]
        dummy_root=SimpleNamespace(deiconify=lambda:None,lift=lambda:None,focus_force=lambda:None)
        host=SimpleNamespace(root=dummy_root,_apply_primary_document_path=lambda path,**kwargs:chosen.append(path) or True)
        with patch("patient_registry_mixin.simpledialog.askinteger",return_value=2) as prompt:
            assert PatientRegistryMixin._load_registry_primary_document(host,entry)
            assert Path(chosen[-1])==b
            assert prompt.call_count==1
        with patch("patient_registry_mixin.simpledialog.askinteger",return_value=None):
            assert not PatientRegistryMixin._load_registry_primary_document(host,entry)
            assert len(chosen)==1

if __name__=="__main__":
    test_missing_address_across_selected_documents()
    test_missing_section_no_and_empty_yes()
    test_choose_source_on_open()
    print("NOV02 CLINICIAN UI REGRESSION: PASS")
