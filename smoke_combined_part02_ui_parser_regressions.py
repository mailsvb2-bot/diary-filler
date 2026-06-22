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
