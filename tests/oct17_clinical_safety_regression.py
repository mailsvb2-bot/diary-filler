"""Physician-facing missing-section warning and DOCX wording regressions."""
from pathlib import Path
from types import SimpleNamespace
from medical_models import PatientData
from medical_expert import build_expert_anamnesis
from medical_formatting import format_staff_short_name
from diary_constants import FINAL_DIARY_TEXT
import actions_creation_orchestrator as orch

def main():
    data=PatientData(complaints="",life_anamnesis="yes",disease_anamnesis="yes",
                     mental_status="",somatic_status="yes",diagnosis="F32.1")
    assert data.empty_required_sections()==["Жалобы","Психический статус"]
    logs=[]
    host=SimpleNamespace(data=data,diagnosis_var=SimpleNamespace(get=lambda:"F32.1"),
                         _popup_diagnosis_override="",_log=logs.append,root=None)
    original=orch.messagebox.askyesno
    called=[]
    def ask(title,msg,**kwargs):
        called.append((title,msg,kwargs))
        return False
    orch.messagebox.askyesno=ask
    try:
        assert orch.ActionsCreationOrchestratorMixin._confirm_empty_required_sections(host) is False
        assert "Жалобы" in called[-1][1] and "Психический статус" in called[-1][1]
        assert called[-1][2]["default"]=="no"
    finally:
        orch.messagebox.askyesno=original
    for number in ("","123456789"):
        source=PatientData(expert_work_status="да",expert_work_org="ООО Завод",expert_position="инженер",
            expert_sick_leave_needed="да",expert_sick_leave_from="15.06.2026",
            expert_sick_leave_number=number,admission_date="10.06.2026",discharge_date="20.06.2026")
        rendered=build_expert_anamnesis(source)
        expect=f"Больничный лист{' № '+number if number else ''} открыт с 15.06.2026."
        assert expect in rendered,rendered
        assert "Больничный лист. Больничный лист" not in rendered
        assert "Срок лечения с 10.06.2026 по 20.06.2026" in rendered
    for raw,expected in (("Балаганин С.В","Балаганин С.В."),
                         ("Можарова е.а","Можарова Е.А."),
                         ("Маркер ИО","Маркер И.О.")):
        assert format_staff_short_name(raw)==expected,(raw,format_staff_short_name(raw))
    assert FINAL_DIARY_TEXT.endswith("Даны рекомендации.")
    s=(Path(__file__).resolve().parents[1]/"actions_creation_orchestrator.py").read_text(encoding="utf-8")
    generation = s[s.index("def _create_selected_outputs_impl("):]
    assert "if selected_medical and not self._confirm_empty_required_sections():" not in generation
    assert "if not self._resolve_unrecognized_generation_fields(generation_patient_data, selected_medical):" in generation
    assert "_missing_clinical_fields_for_popup(data)" in s
    assert "messagebox.askyesnocancel(" in s
    print("OCT17 CLINICAL SAFETY REGRESSION OK")
if __name__=="__main__":main()
