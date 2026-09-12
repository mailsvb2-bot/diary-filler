from app_config import DIARY_KIND
# --- UI sick-leave popup regression ---
class _FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


ui_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
ui_logic.output_vars = {"discharge": _FakeVar(True)}
ui_logic.expert_work_status_var = _FakeVar("")
ui_logic.expert_work_org_var = _FakeVar("ООО Тест")
ui_logic.expert_position_var = _FakeVar("врач")
ui_logic.expert_sick_leave_needed_var = _FakeVar("нет")
ui_logic.expert_sick_leave_from_var = _FakeVar("15.06.2026")
ui_logic.expert_sick_leave_number_var = _FakeVar("")
ui_logic.discharge_date_var = _FakeVar("")
ui_logic._popup_discharge_date_override = ""
ui_logic._manual_discharge_date = False
ui_logic._set_ui_var = lambda var, value: var.set(value)
ui_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(ui_logic, _main_module.CombinedMedicalDiaryApp)
ui_logic._prompt_expert_anamnesis_details = lambda force=False: True
ui_logic._update_expert_sick_leave_display = lambda: None
ui_logic._redraw_selection_controls = lambda: None
number_popup_calls = []
date_popup_calls = []
ui_logic._prompt_discharge_sick_leave_number = lambda: number_popup_calls.append("number") or True
def _fake_discharge_date_popup():
    date_popup_calls.append("date")
    ui_logic.discharge_date_var.set("11.06.2026")
    ui_logic._popup_discharge_date_override = "11.06.2026"
    ui_logic._manual_discharge_date = True
    return True
ui_logic._prompt_discharge_date = _fake_discharge_date_popup
def _fake_discharge_output_requirements():
    date_popup_calls.append("date")
    number_popup_calls.append("number")
    ui_logic.discharge_date_var.set("11.06.2026")
    ui_logic._popup_discharge_date_override = "11.06.2026"
    ui_logic.expert_sick_leave_number_var.set("123456")
    ui_logic._manual_discharge_date = True
    return True
ui_logic._prompt_discharge_output_requirements = _fake_discharge_output_requirements
ui_logic._on_expert_sick_leave_fill()
assert ui_logic.expert_sick_leave_needed_var.get() == "да"
assert number_popup_calls == [], "Number popup must not open from the sick-leave Yes button"
assert ui_logic._ensure_discharge_sick_leave_number(prompt_if_needed=True) is True
assert number_popup_calls == ["number"], "Number popup must open only from discharge flow"
number_popup_calls.clear()
ui_logic.output_vars["discharge"].set(False)
assert ui_logic._ensure_discharge_sick_leave_number(prompt_if_needed=True) is True
assert number_popup_calls == [], "Number popup must not open when discharge is not selected"

# If discharge is already selected (default UI state), clicking the discharge
# tile must complete missing discharge requirements instead of silently
# deselecting the tile: first date, then sick-leave number when needed.
ui_logic.output_vars["discharge"].set(True)
ui_logic.expert_sick_leave_needed_var.set("да")
ui_logic.expert_sick_leave_number_var.set("")
ui_logic.discharge_date_var.set("")
ui_logic._popup_discharge_date_override = ""
number_popup_calls.clear()
date_popup_calls.clear()
ui_logic._update_selected_outputs_status = lambda: None
ui_logic._activate_output_tile = _main_module.CombinedMedicalDiaryApp._activate_output_tile.__get__(ui_logic, _main_module.CombinedMedicalDiaryApp)
ui_logic._activate_output_tile("discharge")
assert date_popup_calls == ["date"], "Discharge tile click must request discharge date when it is missing"
assert number_popup_calls == ["number"], "Discharge tile click must request sick-leave number when both conditions are true"
assert ui_logic.output_vars["discharge"].get() is True, "Discharge must remain selected while completing its required fields"

# Date of discharge is shared: it is required not only for discharge summary,
# but also for diaries and RVK act.
ui_logic.discharge_date_var.set("")
ui_logic._popup_discharge_date_override = ""
ui_logic.output_vars = {"discharge": _FakeVar(False), "rvk": _FakeVar(True), DIARY_KIND: _FakeVar(False)}
assert ui_logic._should_prompt_discharge_date() is True, "RVK tile must request discharge date"
ui_logic.output_vars = {"discharge": _FakeVar(False), "rvk": _FakeVar(False), DIARY_KIND: _FakeVar(True)}
assert ui_logic._should_prompt_discharge_date() is True, "Diaries tile must request discharge date"
ui_logic.output_vars = {"discharge": _FakeVar(False), "rvk": _FakeVar(False), DIARY_KIND: _FakeVar(False)}
assert ui_logic._should_prompt_discharge_date() is False, "Discharge date popup must not open without required outputs"

# Common popup merge regression: for restored/programmatic selections without
# discharge/RVK, treatment/referral details and diary discharge date must be one
# popup, not two consecutive popups.
common_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
common_logic.case_number_var = _FakeVar("")
common_logic.assigned_treatment_var = _FakeVar("")
common_logic.diagnosis_var = _FakeVar("")
common_logic.discharge_date_var = _FakeVar("")
common_logic._popup_discharge_date_override = ""
common_logic._manual_discharge_date = False
common_logic._manual_diagnosis = False
common_logic.data = PatientData()
common_logic.output_vars = {"discharge": _FakeVar(False), "rvk": _FakeVar(False), DIARY_KIND: _FakeVar(True)}
common_logic._set_ui_var = lambda var, value: var.set(value)
common_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(common_logic, _main_module.CombinedMedicalDiaryApp)
common_logic._selected_outputs_require_discharge_date = _main_module.CombinedMedicalDiaryApp._selected_outputs_require_discharge_date.__get__(common_logic, _main_module.CombinedMedicalDiaryApp)
common_logic._discharge_date_missing_or_invalid = _main_module.CombinedMedicalDiaryApp._discharge_date_missing_or_invalid.__get__(common_logic, _main_module.CombinedMedicalDiaryApp)
common_logic._store_discharge_date_value = _main_module.CombinedMedicalDiaryApp._store_discharge_date_value.__get__(common_logic, _main_module.CombinedMedicalDiaryApp)
common_logic._normalize_popup_diagnosis_value = lambda value: value
common_logic._case_number_popup_default = lambda: ""
common_logic._treatment_popup_default = lambda: ""
common_logic._discharge_popup_default = lambda: ""
common_logic._hospitalization_details_missing = lambda: True
common_logic._manual_treatment_missing = lambda: False
common_popup_calls = []
common_logic._prompt_fields = lambda title, rows, width=72: common_popup_calls.append((title, rows)) or ["123", "терапия", "F41.2 тест", "11062026"]
common_logic._prompt_common_output_requirements = _main_module.CombinedMedicalDiaryApp._prompt_common_output_requirements.__get__(common_logic, _main_module.CombinedMedicalDiaryApp)
assert common_logic._prompt_common_output_requirements(include_discharge_date=True) is True
assert len(common_popup_calls) == 1
assert [label for label, _default in common_popup_calls[0][1]] == ["Номер истории болезни", "Лечение", "Диагноз", "Дата выписки"]
assert common_logic.case_number_var.get() == "123"
assert common_logic.assigned_treatment_var.get() == "терапия"
assert common_logic.diagnosis_var.get() == "F41.2 тест"
assert common_logic.discharge_date_var.get() == "11.06.2026"

# Discharge popup owns the explicit episode-occurrence fact. It must ask even
# when every other discharge requirement is already complete, and store the
# canonical value in both session state and PatientData.
occurrence_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
occurrence_logic.admission_occurrence_var = _FakeVar("")
occurrence_logic.data = PatientData()
occurrence_logic._hospitalization_details_missing = lambda: False
occurrence_logic._manual_treatment_missing = lambda: False
occurrence_logic._selected_outputs_require_discharge_date = lambda: False
occurrence_logic._should_prompt_discharge_sick_leave_number = lambda: False
occurrence_logic._case_number_missing = lambda: False
occurrence_logic._current_admission_occurrence = _main_module.CombinedMedicalDiaryApp._current_admission_occurrence.__get__(occurrence_logic, _main_module.CombinedMedicalDiaryApp)
occurrence_logic._store_admission_occurrence_value = _main_module.CombinedMedicalDiaryApp._store_admission_occurrence_value.__get__(occurrence_logic, _main_module.CombinedMedicalDiaryApp)
occurrence_calls = []
occurrence_logic._prompt_fields = lambda title, rows, width=72, choice_options=None: occurrence_calls.append((title, rows, choice_options)) or ["повторно"]
occurrence_logic._prompt_discharge_output_requirements = _main_module.CombinedMedicalDiaryApp._prompt_discharge_output_requirements.__get__(occurrence_logic, _main_module.CombinedMedicalDiaryApp)
assert occurrence_logic._prompt_discharge_output_requirements() is True
assert [label for label, _default in occurrence_calls[0][1]] == ["Поступает в 3 отделение КДП"]
assert occurrence_calls[0][2] == {"Поступает в 3 отделение КДП": ("первично", "повторно")}
assert occurrence_logic.admission_occurrence_var.get() == "повторно"
assert occurrence_logic.data.admission_occurrence == "повторно"

from dialog_document_details import _sync_custom_commissariat_value

manual_commissariat = _FakeVar("старое значение")
manual_commissariat_entry = _FakeVar("военного комиссариата Нижегородской области")
_sync_custom_commissariat_value(manual_commissariat, manual_commissariat_entry)
assert manual_commissariat.get() == "военного комиссариата Нижегородской области"
manual_commissariat_entry.set("")
_sync_custom_commissariat_value(manual_commissariat, manual_commissariat_entry)
assert manual_commissariat.get() == "", "erasing the custom field must clear the selected commissariat"
manual_commissariat.set("Автозаводский")
_sync_custom_commissariat_value(manual_commissariat, manual_commissariat_entry, suppress=True)
assert manual_commissariat.get() == "Автозаводский", "predefined button selection must survive custom-field clearing"

# The shared popup used by primary/commission/admission-doctor must persist the
# same checkbox selection; otherwise the service boundary rejects generation.
common_occurrence_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
common_occurrence_logic.admission_occurrence_var = _FakeVar("")
common_occurrence_logic.data = PatientData()
common_occurrence_logic._hospitalization_details_missing = lambda: False
common_occurrence_logic._manual_treatment_missing = lambda: False
common_occurrence_logic._selected_outputs_require_discharge_date = lambda: False
common_occurrence_logic._case_number_missing = lambda: False
common_occurrence_logic._current_admission_occurrence = _main_module.CombinedMedicalDiaryApp._current_admission_occurrence.__get__(common_occurrence_logic, _main_module.CombinedMedicalDiaryApp)
common_occurrence_logic._store_admission_occurrence_value = _main_module.CombinedMedicalDiaryApp._store_admission_occurrence_value.__get__(common_occurrence_logic, _main_module.CombinedMedicalDiaryApp)
common_occurrence_calls = []
common_occurrence_logic._prompt_fields = lambda title, rows, width=72, choice_options=None: common_occurrence_calls.append((title, rows, choice_options)) or ["первично"]
common_occurrence_logic._prompt_common_output_requirements = _main_module.CombinedMedicalDiaryApp._prompt_common_output_requirements.__get__(common_occurrence_logic, _main_module.CombinedMedicalDiaryApp)
assert common_occurrence_logic._prompt_common_output_requirements(
    include_discharge_date=False,
    include_case_number=False,
    include_medical_details=False,
    include_admission_occurrence=True,
) is True
assert common_occurrence_calls[0][2] == {"Поступает в 3 отделение КДП": ("первично", "повторно")}
assert common_occurrence_logic.admission_occurrence_var.get() == "первично"
assert common_occurrence_logic.data.admission_occurrence == "первично"

# Hospitalization referral popup must not request discharge date unless the
# selected outputs actually need it.
referral_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
referral_logic.primary_document_type_var = _FakeVar("hospitalization_referral")
referral_logic.case_number_var = _FakeVar("")
referral_logic.assigned_treatment_var = _FakeVar("")
referral_logic.diagnosis_var = _FakeVar("")
referral_logic.discharge_date_var = _FakeVar("")
referral_logic._popup_discharge_date_override = ""
referral_logic._manual_discharge_date = False
referral_logic._manual_diagnosis = False
referral_logic.data = PatientData()
referral_logic.output_vars = {"discharge": _FakeVar(False), "rvk": _FakeVar(False), DIARY_KIND: _FakeVar(False)}
referral_logic.status_label = type("Status", (), {"config": lambda self, **kwargs: None})()
referral_logic._set_ui_var = lambda var, value: var.set(value)
referral_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(referral_logic, _main_module.CombinedMedicalDiaryApp)
referral_logic._selected_outputs_require_discharge_date = _main_module.CombinedMedicalDiaryApp._selected_outputs_require_discharge_date.__get__(referral_logic, _main_module.CombinedMedicalDiaryApp)
referral_logic._discharge_date_missing_or_invalid = _main_module.CombinedMedicalDiaryApp._discharge_date_missing_or_invalid.__get__(referral_logic, _main_module.CombinedMedicalDiaryApp)
referral_logic._store_discharge_date_value = _main_module.CombinedMedicalDiaryApp._store_discharge_date_value.__get__(referral_logic, _main_module.CombinedMedicalDiaryApp)
referral_logic._prompt_primary_exam_details_if_needed = lambda force=False: True
referral_logic._normalize_popup_diagnosis_value = lambda value: value
referral_logic._case_number_popup_default = lambda: ""
referral_logic._treatment_popup_default = lambda: ""
referral_logic._discharge_popup_default = lambda: ""
referral_popup_calls = []
referral_logic._prompt_fields = lambda title, rows, width=72: referral_popup_calls.append((title, rows)) or ["321", "лечение", "F20.0 тест"]
referral_logic._prompt_assigned_treatment_if_needed = _main_module.CombinedMedicalDiaryApp._prompt_assigned_treatment_if_needed.__get__(referral_logic, _main_module.CombinedMedicalDiaryApp)
assert referral_logic._prompt_assigned_treatment_if_needed(force=True) is True
assert [label for label, _default in referral_popup_calls[0][1]] == ["Номер истории болезни", "Лечение", "Диагноз"]


# Shared case-number regression: every block-03 medical popup includes the
# same «Номер истории болезни» field; diaries stay excluded.
case_dialog_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
case_dialog_logic.data = PatientData(case_number="77")
case_dialog_logic.case_number_var = _FakeVar("")
case_dialog_logic.commission_date_var = _FakeVar("")
case_dialog_logic.commission_number_var = _FakeVar("")
case_dialog_logic._today_str = lambda: "21.06.2026"
case_dialog_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(case_dialog_logic, _main_module.CombinedMedicalDiaryApp)
case_dialog_logic._case_number_popup_default = _main_module.CombinedMedicalDiaryApp._case_number_popup_default.__get__(case_dialog_logic, _main_module.CombinedMedicalDiaryApp)
case_dialog_logic._store_case_number_value = _main_module.CombinedMedicalDiaryApp._store_case_number_value.__get__(case_dialog_logic, _main_module.CombinedMedicalDiaryApp)
case_dialog_logic._remember_committee_dates = lambda **kwargs: None
commission_rows = []
case_dialog_logic._prompt_fields = lambda title, rows, linked_groups=None, width=28: commission_rows.append((title, rows)) or ["88", "21062026", "5"]
case_dialog_logic._prompt_commission_details = _main_module.CombinedMedicalDiaryApp._prompt_commission_details.__get__(case_dialog_logic, _main_module.CombinedMedicalDiaryApp)
assert case_dialog_logic._prompt_commission_details() is True
assert [label for label, _default in commission_rows[0][1]][0] == "Номер истории болезни"
assert commission_rows[0][1][0][1] == "77"
assert case_dialog_logic.case_number_var.get() == "88"
assert case_dialog_logic.data.case_number == "88"

vk_rows = []
case_dialog_logic.vk_date_var = _FakeVar("")
case_dialog_logic.vk_protocol_number_var = _FakeVar("")
case_dialog_logic.vk_protocol_date_var = _FakeVar("")
case_dialog_logic.vk_mse_work_org_var = _FakeVar("")
case_dialog_logic.vk_mse_position_var = _FakeVar("")
case_dialog_logic._shared_work_defaults = lambda: ("ООО Тест", "инженер")
case_dialog_logic._sync_shared_work_details = lambda org, position: None
case_dialog_logic._prompt_fields = lambda title, rows, width=64, linked_groups=None: vk_rows.append((title, rows, linked_groups)) or ["99", "22062026", "12", "22062026", "ООО Тест", "инженер"]
case_dialog_logic._prompt_vk_mse_details = _main_module.CombinedMedicalDiaryApp._prompt_vk_mse_details.__get__(case_dialog_logic, _main_module.CombinedMedicalDiaryApp)
assert case_dialog_logic._prompt_vk_mse_details() is True
assert [label for label, _default in vk_rows[0][1]][0] == "Номер истории болезни"
assert [label for label, _default in vk_rows[0][1]][1] == "Дата ВК на МСЭ"
assert vk_rows[0][1][0][1] == "88"
assert vk_rows[0][2] == [(1, [3])]
assert case_dialog_logic.case_number_var.get() == "99"
assert case_dialog_logic.data.case_number == "99"

diary_only_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
diary_only_logic.case_number_var = _FakeVar("")
diary_only_logic.assigned_treatment_var = _FakeVar("")
diary_only_logic.diagnosis_var = _FakeVar("")
diary_only_logic.discharge_date_var = _FakeVar("")
diary_only_logic._popup_discharge_date_override = ""
diary_only_logic._manual_discharge_date = False
diary_only_logic.data = PatientData()
diary_only_logic.output_vars = {"discharge": _FakeVar(False), "rvk": _FakeVar(False), DIARY_KIND: _FakeVar(True)}
diary_only_logic._set_ui_var = lambda var, value: var.set(value)
diary_only_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(diary_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_only_logic._selected_outputs_require_discharge_date = _main_module.CombinedMedicalDiaryApp._selected_outputs_require_discharge_date.__get__(diary_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_only_logic._discharge_date_missing_or_invalid = _main_module.CombinedMedicalDiaryApp._discharge_date_missing_or_invalid.__get__(diary_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_only_logic._store_discharge_date_value = _main_module.CombinedMedicalDiaryApp._store_discharge_date_value.__get__(diary_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_only_logic._case_number_missing = lambda: True
diary_only_logic._case_number_popup_default = lambda: ""
diary_only_logic._hospitalization_details_missing = lambda: False
diary_only_logic._manual_treatment_missing = lambda: False
diary_only_logic._discharge_popup_default = lambda: ""
diary_popup_calls = []
diary_only_logic._prompt_fields = lambda title, rows, width=72: diary_popup_calls.append((title, rows)) or ["11062026"]
diary_only_logic._prompt_common_output_requirements = _main_module.CombinedMedicalDiaryApp._prompt_common_output_requirements.__get__(diary_only_logic, _main_module.CombinedMedicalDiaryApp)
assert diary_only_logic._prompt_common_output_requirements(include_discharge_date=True, include_case_number=False, include_medical_details=False) is True
assert [label for label, _default in diary_popup_calls[0][1]] == ["Дата выписки"]
assert diary_only_logic.case_number_var.get() == ""

# Even if the primary document is a hospitalization referral with missing
# treatment/diagnosis, selecting only «Дневники» must ask only discharge date.
diary_referral_only_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
diary_referral_only_logic.case_number_var = _FakeVar("")
diary_referral_only_logic.assigned_treatment_var = _FakeVar("")
diary_referral_only_logic.diagnosis_var = _FakeVar("")
diary_referral_only_logic.discharge_date_var = _FakeVar("")
diary_referral_only_logic._popup_discharge_date_override = ""
diary_referral_only_logic._manual_discharge_date = False
diary_referral_only_logic.data = PatientData()
diary_referral_only_logic.output_vars = {"discharge": _FakeVar(False), "rvk": _FakeVar(False), DIARY_KIND: _FakeVar(True)}
diary_referral_only_logic._set_ui_var = lambda var, value: var.set(value)
diary_referral_only_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(diary_referral_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_referral_only_logic._selected_outputs_require_discharge_date = _main_module.CombinedMedicalDiaryApp._selected_outputs_require_discharge_date.__get__(diary_referral_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_referral_only_logic._discharge_date_missing_or_invalid = _main_module.CombinedMedicalDiaryApp._discharge_date_missing_or_invalid.__get__(diary_referral_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_referral_only_logic._store_discharge_date_value = _main_module.CombinedMedicalDiaryApp._store_discharge_date_value.__get__(diary_referral_only_logic, _main_module.CombinedMedicalDiaryApp)
diary_referral_only_logic._case_number_missing = lambda: True
diary_referral_only_logic._case_number_popup_default = lambda: ""
diary_referral_only_logic._hospitalization_details_missing = lambda: True
diary_referral_only_logic._manual_treatment_missing = lambda: True
diary_referral_only_logic._discharge_popup_default = lambda: ""
diary_referral_only_calls = []
diary_referral_only_logic._prompt_fields = lambda title, rows, width=72: diary_referral_only_calls.append((title, rows)) or ["12062026"]
diary_referral_only_logic._prompt_common_output_requirements = _main_module.CombinedMedicalDiaryApp._prompt_common_output_requirements.__get__(diary_referral_only_logic, _main_module.CombinedMedicalDiaryApp)
assert diary_referral_only_logic._prompt_common_output_requirements(include_discharge_date=True, include_case_number=False, include_medical_details=False) is True
assert [label for label, _default in diary_referral_only_calls[0][1]] == ["Дата выписки"]
assert diary_referral_only_logic.assigned_treatment_var.get() == ""
assert diary_referral_only_logic.diagnosis_var.get() == ""

# --- Deep popup date contract: required dates must be normalized or rejected ---
from tkinter import messagebox as _date_contract_messagebox
_original_date_showwarning = _date_contract_messagebox.showwarning
_date_warnings: list[tuple[str, str]] = []
_date_contract_messagebox.showwarning = lambda title, message, **kwargs: _date_warnings.append((title, message))
try:
    assert case_dialog_logic.commission_date_var.get() == "21.06.2026", case_dialog_logic.commission_date_var.get()
    assert case_dialog_logic.vk_date_var.get() == "22.06.2026", case_dialog_logic.vk_date_var.get()
    assert case_dialog_logic.vk_protocol_date_var.get() == "22.06.2026", case_dialog_logic.vk_protocol_date_var.get()

    bad_date_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
    bad_date_logic.data = PatientData(case_number="77")
    bad_date_logic.case_number_var = _FakeVar("77")
    bad_date_logic.commission_date_var = _FakeVar("")
    bad_date_logic.commission_number_var = _FakeVar("")
    bad_date_logic._today_str = lambda: "21.06.2026"
    bad_date_logic._case_number_popup_default = _main_module.CombinedMedicalDiaryApp._case_number_popup_default.__get__(bad_date_logic, _main_module.CombinedMedicalDiaryApp)
    bad_date_logic._store_case_number_value = _main_module.CombinedMedicalDiaryApp._store_case_number_value.__get__(bad_date_logic, _main_module.CombinedMedicalDiaryApp)
    bad_date_logic._remember_committee_dates = lambda **kwargs: None
    bad_date_logic._prompt_fields = lambda title, rows, linked_groups=None, width=28: ["77", "99.99.2026", "5"]
    assert bad_date_logic._prompt_commission_details() is False
    assert bad_date_logic.commission_date_var.get() == ""
    assert any("Некорректная дата" in title for title, _message in _date_warnings)

    rvk_date_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
    rvk_date_logic.data = PatientData(admission_date="10.06.2026")
    rvk_date_logic.discharge_date_var = _FakeVar("")
    rvk_date_logic.admission_date_var = _FakeVar("10.06.2026")
    rvk_date_logic._popup_discharge_date_override = ""
    rvk_date_logic._manual_discharge_date = False
    rvk_date_logic._set_ui_var = lambda var, value: var.set(value)
    assert rvk_date_logic._store_discharge_date_value("09.06.2026") is False
    assert rvk_date_logic.discharge_date_var.get() == ""
    assert rvk_date_logic._store_discharge_date_value("11062026") is True
    assert rvk_date_logic.discharge_date_var.get() == "11.06.2026"
finally:
    _date_contract_messagebox.showwarning = _original_date_showwarning


# --- Generic popup compact-date submit regression ---
# Mouse-clicking OK must normalize compact dates even when the entry never
# received Return/FocusOut. This is the exact path that previously still made
# the doctor type dots manually in popup windows.
from dialog_fields_core import normalize_prompt_field_values
popup_date_submit = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
normalized_popup_values = normalize_prompt_field_values(
    popup_date_submit,
    [("Дата выписки", ""), ("От / дата протокола / Дата протокола", ""), ("Лечение", "")],
    ["090926", "09092026", "без изменений"],
)
assert normalized_popup_values == ["09.09.2026", "09.09.2026", "без изменений"], normalized_popup_values
assert normalize_prompt_field_values(
    popup_date_submit, [("Дата комиссии", "")], ["99.99.26"]
) == ["99.99.26"], "invalid input must remain available for the normal validator warning"


# --- Shared clinical popup behavior regression ---
clinical_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
clinical_logic.expert_sick_leave_needed_var = _FakeVar("")
clinical_logic.expert_sick_leave_from_var = _FakeVar("")
clinical_logic.expert_sick_leave_number_var = _FakeVar("")
clinical_logic.disability_needed_var = _FakeVar("")
clinical_logic.epi_present_var = _FakeVar("")
clinical_logic.epi_path_var = _FakeVar("")
clinical_logic.admission_date_var = _FakeVar("10.06.2026")
clinical_logic.data = PatientData(admission_date="10.06.2026")
clinical_logic._update_expert_sick_leave_display = lambda: None
clinical_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(clinical_logic, _main_module.CombinedMedicalDiaryApp)
clinical_prompts = []
def _clinical_prompt(title, rows, width=46, linked_groups=None, choice_options=None):
    clinical_prompts.append((title, list(rows), choice_options))
    if title == "Дополнительные данные":
        values = {
            "Нужен ли больничный лист": "да",
            "Нужно ли оформление инвалидности": "нет",
            "Есть ли ЭПИ": "нет",
        }
        return [values[label] for label, _ in rows]
    if title == "Больничный лист":
        return ["12062026"]
    raise AssertionError((title, rows))
clinical_logic._prompt_fields = _clinical_prompt
assert clinical_logic._prompt_shared_clinical_options_if_needed(["primary", "commission"]) is True
assert clinical_logic.expert_sick_leave_needed_var.get() == "да"
assert clinical_logic.expert_sick_leave_from_var.get() == "12.06.2026"
assert clinical_logic.disability_needed_var.get() == "нет"
assert clinical_logic.epi_present_var.get() == "нет"
assert clinical_logic.epi_path_var.get() == ""
assert clinical_logic.data.disability == "не нужно"
assert [call[0] for call in clinical_prompts] == ["Дополнительные данные", "Больничный лист"]
choices = clinical_prompts[0][2]
assert choices["Нужен ли больничный лист"] == ("нет", "да")
assert choices["Нужно ли оформление инвалидности"] == ("нет", "да")
assert choices["Есть ли ЭПИ"] == ("нет", "да")

# The same patient may regenerate a document and correct a previous decision.
# Because the permanent UI controls were intentionally removed, the popup must
# appear again with current values rather than silently locking the first answer.
revision_rows = []
def _revision_prompt(title, rows, width=46, linked_groups=None, choice_options=None):
    revision_rows.extend(rows)
    return ["нет", "да"]
clinical_logic._prompt_fields = _revision_prompt
assert clinical_logic._prompt_shared_clinical_options_if_needed(["primary"]) is True
assert [initial for _label, initial in revision_rows] == ["да", "нет"], revision_rows
assert clinical_logic.expert_sick_leave_needed_var.get() == "нет"
assert clinical_logic.expert_sick_leave_from_var.get() == ""
assert clinical_logic.disability_needed_var.get() == "да"
assert clinical_logic.data.disability == "нужно"

# A previously valid sick-leave date is only a default, not a lock. Reconfirming
# «Да» must reopen the date question so the doctor can correct it.
date_revision_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
date_revision_logic.expert_sick_leave_needed_var = _FakeVar("да")
date_revision_logic.expert_sick_leave_from_var = _FakeVar("12.06.2026")
date_revision_logic.admission_date_var = _FakeVar("10.06.2026")
date_revision_logic.data = PatientData(admission_date="10.06.2026")
date_revision_logic._update_expert_sick_leave_display = lambda: None
date_revision_logic._normalize_date_for_ui = _main_module.CombinedMedicalDiaryApp._normalize_date_for_ui.__get__(date_revision_logic, _main_module.CombinedMedicalDiaryApp)
date_revision_prompts = []
def _date_revision_prompt(title, rows, width=34, linked_groups=None, choice_options=None):
    date_revision_prompts.append((title, list(rows)))
    assert title == "Больничный лист"
    assert rows == [("С какого числа", "12.06.2026")], rows
    return ["13062026"]
date_revision_logic._prompt_fields = _date_revision_prompt
assert date_revision_logic._prompt_sick_leave_start_date_if_needed() is True
assert date_revision_logic.expert_sick_leave_from_var.get() == "13.06.2026"
assert len(date_revision_prompts) == 1

# Positive EPI selection must use the chosen file and persist its text.
epi_logic = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
epi_logic.expert_sick_leave_needed_var = _FakeVar("нет")
epi_logic.expert_sick_leave_from_var = _FakeVar("")
epi_logic.expert_sick_leave_number_var = _FakeVar("")
epi_logic.disability_needed_var = _FakeVar("нет")
epi_logic.epi_present_var = _FakeVar("")
epi_logic.epi_path_var = _FakeVar("")
epi_logic.admission_date_var = _FakeVar("10.06.2026")
epi_logic.data = PatientData(admission_date="10.06.2026")
epi_logic.service = service
epi_logic._update_expert_sick_leave_display = lambda: None
epi_logic._prompt_fields = lambda title, rows, width=46, linked_groups=None, choice_options=None: ["да"]
epi_logic.choose_epi = lambda: (epi_logic.epi_path_var.set(str(epi)), epi_logic.epi_present_var.set("да"))
assert epi_logic._prompt_shared_clinical_options_if_needed(["commission"]) is True
assert epi_logic.epi_present_var.get() == "да"
assert epi_logic.epi_path_var.get() == str(epi)
assert "EPI_PLACEMENT_SENTINEL_7F31" in epi_logic.data.epi_text

# --- Patient switch isolation regression ---
# Switching from one primary file to another must never reuse patient-specific
# EPI/commission/VK/RVK values or manually selected diary inputs. Reusable
# Texts/Dates folders may remain so the next patient's files can be auto-picked.
patient_switch = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
for name in (
    "assigned_treatment_var", "case_number_var", "admission_occurrence_var", "expert_work_status_var",
    "expert_work_org_var", "expert_position_var", "expert_sick_leave_needed_var",
    "expert_sick_leave_from_var", "expert_sick_leave_number_var", "disability_needed_var",
    "vk_mse_work_org_var", "vk_mse_position_var", "sick_leave_vk_work_org_var",
    "sick_leave_vk_position_var", "sick_leave_vk_work_position_var",
    "patient_name_var", "admission_date_var", "discharge_date_var", "diagnosis_var",
    "admission_occurrence_var", "rvk_act_number_var", "rvk_military_commissariat_var", "rvk_work_position_var",
    "vk_date_var", "vk_protocol_number_var", "vk_protocol_date_var",
    "sick_leave_vk_date_var", "sick_leave_vk_protocol_number_var",
    "sick_leave_vk_protocol_date_var", "sick_leave_vk_commission_date_var",
    "commission_date_var", "commission_number_var", "epi_path_var", "epi_present_var",
):
    setattr(patient_switch, name, _FakeVar("OLD"))
patient_switch.expert_sick_leave_needed_var.set("да")
patient_switch.status_files = ["old-patient-texts.docx"]
patient_switch.diary_files = ["old-patient-dates.docx"]
patient_switch.diary_texts_dir = "reusable-texts-folder"
patient_switch.diary_template_dir = "reusable-dates-folder"
patient_switch._diary_text_files_auto_selected = False
patient_switch._diary_files_auto_selected = False
patient_switch._primary_work_org_default = "OLD ORG"
patient_switch._primary_work_position_default = "OLD POSITION"
patient_switch._work_details_manually_edited = True
patient_switch._manual_patient_name = True
patient_switch._manual_admission_date = True
patient_switch._manual_discharge_date = True
patient_switch._manual_diagnosis = True
patient_switch._popup_diagnosis_override = "OLD DIAGNOSIS"
patient_switch._popup_discharge_date_override = "09.09.2026"
patient_switch._last_committee_date = "08.09.2026"
patient_switch._last_protocol_date = "08.09.2026"
patient_switch.data = PatientData(fio="OLD PATIENT")
patient_switch._update_expert_sick_leave_display = lambda: None
patient_switch._update_diary_text_label = lambda **kwargs: None
patient_switch._update_diary_template_label = lambda **kwargs: None
patient_switch._folder_contains_numbered_diary_templates = lambda _folder: False
patient_switch._set_ui_var = lambda var, value: var.set(value)
patient_switch._set_primary_drop_empty = lambda: None
patient_switch._reset_primary_document_runtime_state(clear_patient_inputs=True)
for name in (
    "rvk_act_number_var", "rvk_military_commissariat_var", "rvk_work_position_var",
    "vk_date_var", "vk_protocol_number_var", "vk_protocol_date_var",
    "sick_leave_vk_date_var", "sick_leave_vk_protocol_number_var",
    "sick_leave_vk_protocol_date_var", "sick_leave_vk_commission_date_var",
    "commission_date_var", "commission_number_var", "epi_path_var", "epi_present_var",
):
    assert getattr(patient_switch, name).get() == "", (name, getattr(patient_switch, name).get())
assert patient_switch.status_files == []
assert patient_switch.diary_files == []
assert patient_switch.diary_texts_dir == "reusable-texts-folder"
assert patient_switch.diary_template_dir == "reusable-dates-folder"
assert patient_switch._last_committee_date == ""
assert patient_switch._last_protocol_date == ""

# Before the first primary is chosen, supporting inputs selected intentionally by
# the doctor remain intact; isolation is activated only on an actual patient switch.
first_primary = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
for name in (
    "assigned_treatment_var", "case_number_var", "admission_occurrence_var", "expert_work_status_var",
    "expert_work_org_var", "expert_position_var", "expert_sick_leave_needed_var",
    "expert_sick_leave_from_var", "expert_sick_leave_number_var", "disability_needed_var",
    "vk_mse_work_org_var", "vk_mse_position_var", "sick_leave_vk_work_org_var",
    "sick_leave_vk_position_var", "sick_leave_vk_work_position_var",
    "patient_name_var", "admission_date_var", "discharge_date_var", "diagnosis_var",
    "rvk_act_number_var", "rvk_military_commissariat_var", "rvk_work_position_var",
    "vk_date_var", "vk_protocol_number_var", "vk_protocol_date_var",
    "sick_leave_vk_date_var", "sick_leave_vk_protocol_number_var",
    "sick_leave_vk_protocol_date_var", "sick_leave_vk_commission_date_var",
    "commission_date_var", "commission_number_var", "epi_path_var", "epi_present_var",
):
    setattr(first_primary, name, _FakeVar(""))
first_primary.epi_path_var.set("preselected-epi.docx")
first_primary.epi_present_var.set("да")
first_primary.status_files = ["preselected-texts.docx"]
first_primary.diary_files = ["preselected-dates.docx"]
first_primary.diary_texts_dir = "reusable-texts-folder"
first_primary.diary_template_dir = ""
first_primary._diary_text_files_auto_selected = False
first_primary._diary_files_auto_selected = False
first_primary._primary_work_org_default = ""
first_primary._primary_work_position_default = ""
first_primary._work_details_manually_edited = False
first_primary._manual_patient_name = False
first_primary._manual_admission_date = False
first_primary._manual_discharge_date = False
first_primary._manual_diagnosis = False
first_primary._popup_diagnosis_override = ""
first_primary._popup_discharge_date_override = ""
first_primary._last_committee_date = ""
first_primary._last_protocol_date = ""
first_primary.data = PatientData()
first_primary._update_expert_sick_leave_display = lambda: None
first_primary._update_diary_text_label = lambda **kwargs: None
first_primary._update_diary_template_label = lambda **kwargs: None
first_primary._set_ui_var = lambda var, value: var.set(value)
first_primary._set_primary_drop_empty = lambda: None
first_primary._reset_primary_document_runtime_state(clear_patient_inputs=False)
assert first_primary.epi_path_var.get() == "preselected-epi.docx"
assert first_primary.epi_present_var.get() == "да"
assert first_primary.status_files == ["preselected-texts.docx"]
assert first_primary.diary_files == ["preselected-dates.docx"]

# A manually pinned output folder must not leak silently to the next patient.
# The doctor explicitly chooses whether to keep it; choosing «Нет» restores the
# normal "save beside the new primary DOCX" behavior.
import files_mixin as _files_mixin_module
manual_output = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
manual_output._manual_output_dir = True
manual_output.output_dir_var = _FakeVar(r"C:\old-patient")
_original_askyesno = _files_mixin_module.messagebox.askyesno
try:
    _files_mixin_module.messagebox.askyesno = lambda *_a, **_k: False
    assert manual_output._confirm_manual_output_dir_for_patient_switch() is False
    assert manual_output._manual_output_dir is False
    manual_output._manual_output_dir = True
    _files_mixin_module.messagebox.askyesno = lambda *_a, **_k: True
    assert manual_output._confirm_manual_output_dir_for_patient_switch() is True
    assert manual_output._manual_output_dir is True
finally:
    _files_mixin_module.messagebox.askyesno = _original_askyesno

# --- Primary selected status layout regression ---
layout_sources_text = Path("layout_sources.py").read_text(encoding="utf-8")
files_mixin_text = Path("files_mixin.py").read_text(encoding="utf-8")
assert 'primary_selected_status_var = tk.StringVar(value=" ")' in layout_sources_text
assert 'primary_drop_hint_label' in layout_sources_text
assert 'drop.grid_propagate(False)' in layout_sources_text
assert 'drop_height = self._px(96 if self._compact_ui else 106, 78)' in layout_sources_text
assert 'self.primary_drop_hint_label.config(text="", fg=FIELD)' in layout_sources_text
assert 'self.primary_drop_hint_label.grid_remove()' not in layout_sources_text
assert 'Path(path).name' in files_mixin_text
assert 'primary_selected_status_label.grid_remove()' not in files_mixin_text
assert 'primary_selected_status_label.grid()' not in files_mixin_text
assert 'def _truncate_label_text' in files_mixin_text
assert 'self._confirm_manual_output_dir_for_patient_switch()' in files_mixin_text
assert ('single_line=self._compact_ui' in Path("dnd_mixin.py").read_text(encoding="utf-8") or '_update_diary_text_label(success=True)' in Path("dnd_mixin.py").read_text(encoding="utf-8"))
from files_mixin import FilesMixin
_long_name = "Очень длинное название первичного документа пациента Иванова Ирина Ивановна 10052026.docx"
assert "…" in FilesMixin._truncate_label_text(_long_name, max_chars=40)

# --- Deep audit hardening regressions ---
from typing import get_type_hints
from diary_table_numbers import should_remove_holiday
from medical_docx_date_patterns import _first_valid_full_date as _title_date_first
assert get_type_hints(should_remove_holiday)["row_date"]
assert _title_date_first("10052026") == "10.05.2026"
assert _title_date_first("1126") == "01.01.2026"
assert "if not query:" in Path("diagnosis_widget.py").read_text(encoding="utf-8")
assert "if not query:" in Path("dialog_fields_popup.py").read_text(encoding="utf-8")
assert "_select_default_printer_sync" in Path("actions_creation_orchestrator.py").read_text(encoding="utf-8")

# --- Small parsing/formatting regressions fixed after audit ---
assert parse_date("12.01.26 г.").strftime("%d.%m.%Y") == "12.01.2026"
assert parse_date("12. 01.2026").strftime("%d.%m.%Y") == "12.01.2026"
assert parse_date("12 .01.26 г.").strftime("%d.%m.%Y") == "12.01.2026"
assert parse_date("10052026").strftime("%d.%m.%Y") == "10.05.2026"
assert parse_date("100526").strftime("%d.%m.%Y") == "10.05.2026"
assert parse_date("1126").strftime("%d.%m.%Y") == "01.01.2026"
assert parse_date("10526").strftime("%d.%m.%Y") == "01.05.2026"
assert parse_date("31126").strftime("%d.%m.%Y") == "31.01.2026"
assert format_date_with_russian_year_suffix("12.01.2026г.") == "12.01.2026 г."
assert format_birth_for_person_line("1980 г.р") == "1980 г.р"
assert format_birth_for_person_line("1980") == "1980 г.р."
assert parse_full_date("11.06.2026 г.").strftime("%d.%m.%Y") == "11.06.2026"
assert parse_full_date("11062026").strftime("%d.%m.%Y") == "11.06.2026"
assert parse_full_date("110626").strftime("%d.%m.%Y") == "11.06.2026"
assert parse_full_date("1126").strftime("%d.%m.%Y") == "01.01.2026"
assert parse_month_year("06.2026 г.") == (6, 2026)
assert format_military_commissariat_area("Канвинский") == "Канавинского района"
assert format_military_commissariat_area("Сормовский\\Московский") == "Сормовского и Московского района"
assert format_military_commissariat_referral("Канвинский") == "По направлению из Канавинского военкомата"
assert format_military_commissariat_referral("Сормовский/Московский") == "По направлению из Сормовского и Московского военкомата"

parser_after_audit = MedicalTextParser()
assert parser_after_audit.parse_text("Не работает").work_org == ""
assert parser_after_audit.parse_text("Работает в организации: не работает").work_org == ""
assert parser_after_audit.parse_text("Место работы: безработный").work_org == ""
parser_work_doctor = parser_after_audit.parse_text("Работает: ООО Ромашка, в должности врач")
assert parser_work_doctor.work_org == "ООО Ромашка", parser_work_doctor.work_org
assert parser_work_doctor.position == "врач", parser_work_doctor.position
parser_position_doctor = parser_after_audit.parse_text("Работает в организации: ООО Ромашка\nДолжность: врач-психиатр")
assert parser_position_doctor.work_org == "ООО Ромашка", parser_position_doctor.work_org
assert parser_position_doctor.position == "врач-психиатр", parser_position_doctor.position

# Имена файлов должны сохраняться с пробелами, без подчеркиваний между словами.
assert _medical_documents_module.safe_filename("Сидоров Иван Михайлович") == "Сидоров Иван Михайлович"
assert _medical_documents_module.safe_filename("Сидоров/Иван:Михайлович") == "Сидоров Иван Михайлович"
assert _medical_documents_module.safe_filename("CON") == "CON_"
assert _medical_documents_module.safe_filename("CON.txt") == "CON.txt_"
assert safe_filename_part("LPT1.docx") == "LPT1.docx_"

from typing import get_type_hints
from medical_formatting import parse_date as _medical_parse_date
assert get_type_hints(_medical_parse_date)["return"]
assert safe_filename_part("NUL") == "NUL_"
assert "Первичный осмотр" in _medical_documents_module.OUTPUT_SUFFIXES["primary"]
assert "Осмотр врача приёмного покоя" in _medical_documents_module.OUTPUT_SUFFIXES["admission_doctor_referral"]
assert _medical_documents_module.TEMPLATE_FILES["admission_doctor_referral"] == "7 Направление врача приёмного покоя.docx"
assert "_" not in _medical_documents_module.OUTPUT_SUFFIXES["discharge"]

# --- Diagnosis parser regression: diagnosis line must not absorb neighboring sections ---
diag_cases = {
    "Диагноз: F20.0 Параноидная шизофрения Жалобы: нет": "F20.0 Параноидная шизофрения",
    "был выставлен диагноз: F41.2 Смешанное тревожное и депрессивное расстройство План лечения: терапия": "F41.2 Смешанное тревожное и депрессивное расстройство",
    "На основании данных анамнеза установлен диагноз: F06.6 Органическое эмоционально лабильное расстройство\nЭпидемиологический анамнез: без особенностей": "F06.6 Органическое эмоционально лабильное расстройство",
    "Диагноз: F": "",
}
for raw_diag, expected_diag in diag_cases.items():
    assert sanitize_diagnosis(raw_diag) == expected_diag, (raw_diag, sanitize_diagnosis(raw_diag))

diag_parse = MedicalTextParser().parse_text(
    "Диагноз: F20.0 Параноидная шизофрения Жалобы: нет Анамнез жизни: тест"
)
assert diag_parse.diagnosis == "F20.0 Параноидная шизофрения", diag_parse.diagnosis

# --- Parser styles regression: demographics in columns and in one compact line ---
parser_style_column = MedicalTextParser().parse_text("""
ФИО: Иванов Иван Иванович
возраст:34 года
Проживает : Г. Нижний Новгород, улица Ленина 34-15
Работает: ООО Завод
""")
assert parser_style_column.fio == "Иванов Иван Иванович", parser_style_column.fio
assert parser_style_column.birth == "34 года", parser_style_column.birth
assert parser_style_column.registered == "Г. Нижний Новгород, улица Ленина 34-15", parser_style_column.registered
assert parser_style_column.work_org == "ООО Завод", parser_style_column.work_org

parser_work_phrase = MedicalTextParser().parse_text("""
10.06.2026 Первичный осмотр
ФИО: Сидоров Иван Михайлович
Работает в Рассвет, в должности Уборщик.
Диагноз: F41.2 тест
""")
assert parser_work_phrase.work_org == "Рассвет", parser_work_phrase.work_org
assert parser_work_phrase.position == "Уборщик", parser_work_phrase.position

parser_work_label_combo = MedicalTextParser().parse_text("""
10.06.2026 Первичный осмотр
ФИО: Сидоров Иван Михайлович
Место работы: ООО «Привет», должность: начальник
Диагноз: F41.2 тест
""")
assert parser_work_label_combo.work_org == "ООО «Привет»", parser_work_label_combo.work_org
assert parser_work_label_combo.position == "начальник", parser_work_label_combo.position

parser_style_line = MedicalTextParser().parse_text(
    "Иванов Иван Иванович, 34 года, Г. Нижний Новгород, улица Ленина 34-15, ООО Завод"
)
assert parser_style_line.fio == "Иванов Иван Иванович", parser_style_line.fio
assert parser_style_line.birth == "34 года", parser_style_line.birth
assert parser_style_line.registered == "Г. Нижний Новгород, улица Ленина 34-15", parser_style_line.registered
assert parser_style_line.work_org == "ООО Завод", parser_style_line.work_org

parser_two_digit_birth = MedicalTextParser().parse_text(
    "Ф.И.О.: Иванов Иван Иванович, Дата рождения: 04.01.80, Место жительства: Н. Новгород, ул. Тестовая, 1"
)
assert parser_two_digit_birth.birth == "04.01.80", parser_two_digit_birth.birth

# --- Compact demographics smoke: ФИО/возраст/адрес can be written in one line ---
