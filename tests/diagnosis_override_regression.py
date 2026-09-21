"""Regression for UI diagnosis authority and diary-text source selection.

The doctor-visible Diagnosis field is authoritative for the complete generation
run. Automatic diary text selection follows that frozen diagnosis; an explicit
Word-file choice pins a manual override. Both modern OOXML and legacy .doc text
sources are part of the supported UI contract.
"""
from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

import diary_batch
import diary_text_parser
import files_mixin
import actions_creation_orchestrator
from actions_medical_flow import ActionsMedicalFlowMixin
from actions_diary_flow import ActionsDiaryFlowMixin
from actions_creation_orchestrator import ActionsCreationOrchestratorMixin
from diary_text_selection import (
    find_diary_text_file_for_diagnosis,
    iter_diary_text_docx_files,
    normalize_diary_diagnosis_name,
)
from files_mixin import FilesMixin
from medical_constants import DOCUMENT_ORDER
from medical_docx_reader import extract_docx_text
from medical_models import PatientData
from tools.generation_performance_profile import _make_fixture


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _SnapshotHarness(ActionsMedicalFlowMixin):
    def _apply_staff_profile_to_patient_data(self, data):
        return data


class _TextHarness(FilesMixin):
    def __init__(self, folder: Path):
        self.folder = folder
        self.diagnosis_var = _Var("")
        self.output_dir_var = _Var("")
        self.status_files: list[str] = []
        self.diary_texts_dir = str(folder)
        self._diary_text_files_auto_selected = False
        self.data = PatientData()
        self.events: list[str] = []

    def _candidate_diary_text_dirs(self):
        return [self.folder]

    def _update_diary_text_label(self, **_kwargs):
        pass

    def _redraw_selection_controls(self):
        pass

    def _remember_dialog_directory(self, *_args, **_kwargs):
        pass

    def _dialog_initial_dir(self, *_args, **_kwargs):
        return str(self.folder)

    def _set_output_dir_auto(self, value):
        self.output_dir_var.set(str(value))

    def _log(self, text):
        self.events.append(text)


class _PatientSwitchHarness(FilesMixin):
    def __init__(self):
        for name, default in (
            files_mixin.PATIENT_SESSION_ALWAYS_VAR_DEFAULTS
            + files_mixin.PATIENT_SESSION_TRACKED_UI_VAR_DEFAULTS
            + files_mixin.PATIENT_SESSION_SWITCH_ONLY_VAR_DEFAULTS
        ):
            setattr(self, name, _Var(copy.deepcopy(default)))
        for name, default in (
            files_mixin.PATIENT_SESSION_ALWAYS_ATTR_DEFAULTS
            + files_mixin.PATIENT_SESSION_SWITCH_ONLY_ATTR_DEFAULTS
        ):
            setattr(self, name, copy.deepcopy(default))
        for name in files_mixin.PATIENT_SESSION_SWITCH_ONLY_LIST_ATTRS:
            setattr(self, name, [])
        self.diary_texts_dir = ""
        self.diary_template_dir = ""
        self.data = PatientData()

    def _set_ui_var(self, var, value):
        var.set(value)

    def _update_expert_sick_leave_display(self):
        pass

    def _update_diary_text_label(self, **_kwargs):
        pass

    def _update_diary_template_label(self, **_kwargs):
        pass

    def _set_primary_drop_empty(self):
        pass


class _DiaryFallbackHarness(ActionsDiaryFlowMixin):
    def __init__(self):
        self.navigation_path_var = _Var("")
        self.diagnosis_var = _Var("F42.2 Смешанные навязчивые мысли и действия")
        self.diary_files = ["dates.docx"]
        self.status_files = []
        self._diary_files_auto_selected = False
        self._diary_text_files_auto_selected = False
        self.diary_texts_dir = "C:/Тексты"
        self.manual_offer = None

    def _auto_select_diary_text_by_diagnosis(self, **_kwargs):
        return False

    def _offer_manual_diary_text_file(self, *, diagnosis="", initial_dir=None):
        self.manual_offer = (diagnosis, str(initial_dir or ""))
        return False


class _PartialSetHarness(ActionsCreationOrchestratorMixin):
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.expert_sick_leave_needed_var = _Var("нет")
        self.printer_var = _Var("")
        self.open_result_folder_var = _Var(False)
        self.logs: list[str] = []
        self.status = ""
        self.reports: list[dict] = []

    def selected_medical_docs(self):
        return ["primary"]

    def diaries_selected(self):
        return True

    def _selected_output_names(self, selected_medical, selected_diaries):
        return [*selected_medical, "diaries"] if selected_diaries else list(selected_medical)

    def _prompt_missing_patient_identity_if_needed(self):
        return True

    def _prompt_shared_clinical_options_if_needed(self, _selected):
        return True

    def _prompt_common_output_requirements(self, **_kwargs):
        return True

    def _selected_docs_need_expert_anamnesis(self, _selected):
        return False

    def _prompt_assigned_treatment_if_needed(self, **_kwargs):
        return True

    def _start_progress(self):
        pass

    def _stop_progress(self):
        pass

    def _result_output_dir(self):
        return self.output_dir

    def _capture_generation_patient_data(self, **_kwargs):
        return PatientData(
            fio="Тестов Тест Тестович",
            output_fio="Тестов Тест Тестович",
            admission_date="01.09.2026",
            discharge_date="05.09.2026",
            diagnosis="F42.2 Смешанные навязчивые мысли и действия",
        )

    def _create_medical_documents_impl(self, _selected, *, output_dir_override, **_kwargs):
        path = Path(output_dir_override) / "Первичный осмотр.docx"
        path.write_bytes(b"medical-document-ok")
        return [path]

    def _create_diaries_impl(self, **_kwargs):
        raise ValueError("Тексты дневников не выбраны")

    def _write_creation_report(self, **kwargs):
        self.reports.append(kwargs)
        return None

    def _open_output_folder_after_creation(self, **_kwargs):
        return False

    def _log(self, text):
        self.logs.append(text)

    def _set_status(self, text):
        self.status = text


def _assert_ui_diagnosis_wins_snapshot() -> None:
    app = _SnapshotHarness()
    app.data = PatientData(fio="Иванов Иван Иванович", diagnosis="F99.9 Старый диагноз из первичного")
    app.navigation_path_var = _Var("")
    app.patient_name_var = _Var("Иванов Иван Иванович")
    app.admission_date_var = _Var("10.06.2026")
    app.discharge_date_var = _Var("11.06.2026")
    app.diagnosis_var = _Var("F20.0 Параноидная шизофрения")
    app._popup_discharge_date_override = ""
    app._popup_diagnosis_override = "F06.8 Старый диагноз из popup"

    snapshot = app._capture_generation_patient_data(require_primary=False)
    assert snapshot.diagnosis == "F20.0 Параноидная шизофрения", snapshot.diagnosis

    app.diagnosis_var.set("Органическое расстройство личности")
    snapshot = app._capture_generation_patient_data(require_primary=False)
    assert snapshot.diagnosis == "Органическое расстройство личности", snapshot.diagnosis


def _assert_all_medical_documents_receive_new_diagnosis(root: Path) -> None:
    nav, service, data = _make_fixture(root)
    old = data.diagnosis
    new = "F20.0 Параноидная шизофрения"
    data.diagnosis = new
    output = root / "medical-diagnosis-override"
    created, used = service.create_documents(
        navigation_path=nav,
        output_dir=output,
        discharge_date=data.discharge_date,
        selected_docs=DOCUMENT_ORDER,
        override_data=data,
    )
    assert used.diagnosis == new
    assert len(created) == len(DOCUMENT_ORDER)
    texts = {path.name: extract_docx_text(path) for path in created}
    joined = "\n".join(texts.values())
    assert old not in joined, f"old diagnosis leaked into generated set: {old!r}"
    for name, text in texts.items():
        assert "Параноидная шизофрения" in text, f"new UI diagnosis missing from {name}"


def _assert_verbal_matching_and_word_formats(root: Path) -> None:
    folder = root / "Тексты"
    folder.mkdir()
    (folder / "F20.0 Органическое расстройство.docx").touch()
    (folder / "шизофрения параноидная.docx").touch()
    (folder / "органическое расстройство личности.doc").touch()
    (folder / "депрессивный эпизод.docm").touch()

    visible = {p.name for p in iter_diary_text_docx_files(folder)}
    assert visible == {
        "F20.0 Органическое расстройство.docx",
        "шизофрения параноидная.docx",
        "органическое расстройство личности.doc",
        "депрессивный эпизод.docm",
    }, visible

    found = find_diary_text_file_for_diagnosis(folder, "F20.0 Параноидная шизофрения")
    assert found is not None and found.name == "шизофрения параноидная.docx", found

    found = find_diary_text_file_for_diagnosis(folder, "F06.8 Органическое расстройство личности")
    assert found is not None and found.name == "органическое расстройство личности.doc", found

    assert normalize_diary_diagnosis_name("F20.0") == ""
    assert find_diary_text_file_for_diagnosis(folder, "F20.0") is None


def _assert_auto_refresh_and_manual_pin(root: Path) -> None:
    folder = root / "auto-texts"
    folder.mkdir()
    old_file = folder / "органическое расстройство личности.docx"
    new_file = folder / "шизофрения параноидная.docx"
    manual_file = folder / "мой выбранный текст.doc"
    for path in (old_file, new_file, manual_file):
        path.touch()

    app = _TextHarness(folder)
    app.status_files = [str(old_file)]
    app._diary_text_files_auto_selected = True
    assert app._auto_select_diary_text_by_diagnosis(
        diagnosis_override="F20.0 Параноидная шизофрения",
        ask_folder=False,
    )
    assert app.status_files == [str(new_file)], app.status_files
    assert app._diary_text_files_auto_selected is True

    assert not app._auto_select_diary_text_by_diagnosis(
        diagnosis_override="Кататоническое состояние редкого типа",
        ask_folder=False,
    )
    assert app.status_files == [], app.status_files

    app.status_files = [str(manual_file)]
    app._diary_text_files_auto_selected = False
    assert app._auto_select_diary_text_by_diagnosis(
        diagnosis_override="F20.0 Параноидная шизофрения",
        ask_folder=False,
    )
    assert app.status_files == [str(manual_file)]
    assert app._diary_text_files_auto_selected is False


def _assert_manual_text_is_patient_scoped(root: Path) -> None:
    manual_file = root / "patient-a-manual-text.docx"
    manual_file.touch()
    app = _PatientSwitchHarness()

    app.status_files = [str(manual_file)]
    app._diary_text_files_auto_selected = False
    app._reset_primary_document_runtime_state(clear_patient_inputs=False)
    assert app.status_files == [str(manual_file)], app.status_files
    assert app._diary_text_files_auto_selected is False

    app.status_files = [str(manual_file)]
    app._diary_text_files_auto_selected = False
    app._reset_primary_document_runtime_state(clear_patient_inputs=True)
    assert app.status_files == [], app.status_files
    assert app._diary_text_files_auto_selected is False


def _assert_full_patient_switch_reset_matrix() -> None:
    """Every high-risk patient-specific field must be owned by the reset contract."""
    required_always_vars = {
        "assigned_treatment_var",
        "case_number_var",
        "admission_occurrence_var",
        "expert_work_status_var",
        "expert_work_org_var",
        "expert_position_var",
        "expert_sick_leave_needed_var",
        "expert_sick_leave_from_var",
        "expert_sick_leave_number_var",
        "disability_needed_var",
        "psych_account_status_var",
        "psych_account_since_year_var",
        "rvk_referral_present_var",
        "rvk_referral_commissariat_var",
        "vk_mse_work_org_var",
        "vk_mse_position_var",
        "sick_leave_vk_work_org_var",
        "sick_leave_vk_position_var",
        "sick_leave_vk_work_position_var",
    }
    required_tracked_ui_vars = {
        "patient_name_var",
        "admission_date_var",
        "discharge_date_var",
        "diagnosis_var",
    }
    required_switch_vars = {
        "rvk_act_number_var",
        "rvk_military_commissariat_var",
        "rvk_work_position_var",
        "vk_date_var",
        "vk_protocol_number_var",
        "vk_protocol_date_var",
        "sick_leave_vk_date_var",
        "sick_leave_vk_protocol_number_var",
        "sick_leave_vk_protocol_date_var",
        "sick_leave_vk_commission_date_var",
        "commission_date_var",
        "commission_number_var",
        "epi_path_var",
        "epi_present_var",
    }
    required_always_attrs = {
        "_primary_work_org_default",
        "_primary_work_position_default",
        "_work_details_manually_edited",
        "_manual_patient_name",
        "_manual_admission_date",
        "_manual_discharge_date",
        "_manual_diagnosis",
        "_popup_diagnosis_override",
        "_popup_discharge_date_override",
        "_popup_fio_override",
        "_popup_birth_override",
    }
    required_switch_attrs = {
        "_last_committee_date",
        "_last_protocol_date",
        "_diary_text_files_auto_selected",
        "_diary_files_auto_selected",
    }
    required_switch_lists = {"status_files", "diary_files"}

    always_vars = dict(files_mixin.PATIENT_SESSION_ALWAYS_VAR_DEFAULTS)
    tracked_ui_vars = dict(files_mixin.PATIENT_SESSION_TRACKED_UI_VAR_DEFAULTS)
    switch_vars = dict(files_mixin.PATIENT_SESSION_SWITCH_ONLY_VAR_DEFAULTS)
    always_attrs = dict(files_mixin.PATIENT_SESSION_ALWAYS_ATTR_DEFAULTS)
    switch_attrs = dict(files_mixin.PATIENT_SESSION_SWITCH_ONLY_ATTR_DEFAULTS)
    switch_lists = set(files_mixin.PATIENT_SESSION_SWITCH_ONLY_LIST_ATTRS)

    assert required_always_vars <= set(always_vars), required_always_vars - set(always_vars)
    assert required_tracked_ui_vars <= set(tracked_ui_vars), required_tracked_ui_vars - set(tracked_ui_vars)
    assert required_switch_vars <= set(switch_vars), required_switch_vars - set(switch_vars)
    assert required_always_attrs <= set(always_attrs), required_always_attrs - set(always_attrs)
    assert required_switch_attrs <= set(switch_attrs), required_switch_attrs - set(switch_attrs)
    assert required_switch_lists <= switch_lists, required_switch_lists - switch_lists

    app = _PatientSwitchHarness()
    for name in required_always_vars | required_tracked_ui_vars | required_switch_vars:
        getattr(app, name).set("PATIENT_A_LEAK")
    for name in required_always_attrs | required_switch_attrs:
        default = always_attrs.get(name, switch_attrs.get(name))
        setattr(app, name, True if isinstance(default, bool) else "PATIENT_A_LEAK")
    app.status_files = ["patient-a-text.docx"]
    app.diary_files = ["patient-a-dates.docx"]
    app.data = PatientData(
        fio="Пациент А",
        admission_date="01.09.2026",
        discharge_date="05.09.2026",
        diagnosis="F99.9 Данные пациента А",
    )

    app._reset_primary_document_runtime_state(clear_patient_inputs=True)

    for name in required_always_vars:
        assert getattr(app, name).get() == always_vars[name], (name, getattr(app, name).get())
    for name in required_tracked_ui_vars:
        assert getattr(app, name).get() == tracked_ui_vars[name], (name, getattr(app, name).get())
    for name in required_switch_vars:
        assert getattr(app, name).get() == switch_vars[name], (name, getattr(app, name).get())
    for name in required_always_attrs:
        assert getattr(app, name) == always_attrs[name], (name, getattr(app, name))
    for name in required_switch_attrs:
        assert getattr(app, name) == switch_attrs[name], (name, getattr(app, name))
    assert app.status_files == []
    assert app.diary_files == []
    assert app.data == PatientData(), app.data


def _assert_manual_picker_accepts_doc(root: Path) -> None:
    folder = root / "manual-picker"
    folder.mkdir()
    legacy = folder / "ручной текст.doc"
    legacy.write_bytes(b"legacy-placeholder")
    app = _TextHarness(folder)

    original = files_mixin.filedialog.askopenfilename
    captured = {}
    try:
        def fake_picker(*_args, **kwargs):
            captured.update(kwargs)
            return str(legacy)

        files_mixin.filedialog.askopenfilename = fake_picker
        app.choose_status_file()
    finally:
        files_mixin.filedialog.askopenfilename = original

    assert app.status_files == [str(legacy)]
    assert app.diary_texts_dir == str(folder)
    assert app._diary_text_files_auto_selected is False
    filetypes_repr = repr(captured.get("filetypes"))
    for suffix in ("*.doc", "*.docx", "*.docm"):
        assert suffix in filetypes_repr, filetypes_repr


def _assert_legacy_doc_parser_route(root: Path) -> None:
    legacy = root / "legacy.doc"
    legacy.write_bytes(b"legacy-placeholder")
    original = diary_text_parser._convert_legacy_doc_to_docx
    try:
        def fake_convert(_source: Path, target: Path) -> None:
            doc = Document()
            doc.add_paragraph("Пациент спокоен, ориентирован, продуктивному контакту доступен.")
            doc.save(target)

        diary_text_parser._convert_legacy_doc_to_docx = fake_convert
        statuses = diary_text_parser.extract_statuses_from_docx(legacy)
    finally:
        diary_text_parser._convert_legacy_doc_to_docx = original
    assert statuses and "Пациент спокоен" in statuses[0]

    original_extract = diary_batch.extract_statuses_from_docx
    try:
        diary_batch.extract_statuses_from_docx = lambda *_args, **_kwargs: [
            "Пациент спокоен, ориентирован, продуктивному контакту доступен."
        ]
        statuses = diary_batch.read_statuses_from_files([legacy])
    finally:
        diary_batch.extract_statuses_from_docx = original_extract
    assert statuses
    try:
        diary_batch._existing_docx_files([legacy], "таблица дневников")
    except ValueError:
        pass
    else:
        raise AssertionError("legacy .doc must not be accepted as a Dates template")


def _assert_failed_auto_match_offers_manual_word_file(root: Path) -> None:
    folder = root / "manual-fallback-texts"
    folder.mkdir()
    manual = folder / "нужный врачом шаблон.docx"
    manual.touch()
    app = _TextHarness(folder)
    app.diagnosis_var.set("F42.2 Смешанные навязчивые мысли и действия")

    original_dir = files_mixin.filedialog.askdirectory
    original_file = files_mixin.filedialog.askopenfilename
    original_yesno = files_mixin.messagebox.askyesno
    captured: dict[str, object] = {"yesno": 0}
    try:
        files_mixin.filedialog.askdirectory = lambda **_kwargs: str(folder)

        def fake_yesno(title, message, **_kwargs):
            captured["yesno"] = int(captured["yesno"]) + 1
            captured["title"] = title
            captured["message"] = message
            return True

        def fake_file(*_args, **kwargs):
            captured["file_kwargs"] = kwargs
            return str(manual)

        files_mixin.messagebox.askyesno = fake_yesno
        files_mixin.filedialog.askopenfilename = fake_file
        app.choose_status_files()
    finally:
        files_mixin.filedialog.askdirectory = original_dir
        files_mixin.filedialog.askopenfilename = original_file
        files_mixin.messagebox.askyesno = original_yesno

    assert captured["yesno"] == 1, captured
    assert "Выбрать нужный файл вручную" in str(captured.get("message", "")), captured
    picker = captured.get("file_kwargs")
    assert isinstance(picker, dict), captured
    assert Path(str(picker.get("initialdir"))).resolve() == folder.resolve(), picker
    filetypes_repr = repr(picker.get("filetypes"))
    assert "*.doc" in filetypes_repr and "*.docx" in filetypes_repr and "*.docm" in filetypes_repr, picker
    assert app.status_files == [str(manual)], app.status_files
    assert app._diary_text_files_auto_selected is False


def _assert_diary_creation_path_offers_manual_fallback() -> None:
    app = _DiaryFallbackHarness()
    snapshot = PatientData(
        fio="Тестов Тест Тестович",
        admission_date="01.09.2026",
        discharge_date="05.09.2026",
        diagnosis="F42.2 Смешанные навязчивые мысли и действия",
    )
    try:
        app._create_diaries_impl(patient_data_snapshot=snapshot)
    except ValueError as exc:
        assert "Тексты дневников не выбраны" in str(exc), exc
    else:
        raise AssertionError("diary flow must stop only after manual fallback was declined")
    assert app.manual_offer is not None
    assert app.manual_offer[0] == snapshot.diagnosis, app.manual_offer


def _assert_diary_failure_keeps_medical_documents(root: Path) -> None:
    output = root / "partial-set-output"
    app = _PartialSetHarness(output)
    original_warning = actions_creation_orchestrator.messagebox.showwarning
    original_error = actions_creation_orchestrator.messagebox.showerror
    warnings: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    try:
        actions_creation_orchestrator.messagebox.showwarning = lambda title, message, **_kwargs: warnings.append((title, message))
        actions_creation_orchestrator.messagebox.showerror = lambda title, message, **_kwargs: errors.append((title, message))
        app.create_selected_outputs(print_after=False)
    finally:
        actions_creation_orchestrator.messagebox.showwarning = original_warning
        actions_creation_orchestrator.messagebox.showerror = original_error

    saved = list(output.glob("Первичный осмотр*.docx"))
    assert len(saved) == 1 and saved[0].read_bytes() == b"medical-document-ok", saved
    assert not errors, errors
    assert warnings and warnings[-1][0] == "Комплект создан частично", warnings
    assert "Дневники" in warnings[-1][1] and "Тексты дневников не выбраны" in warnings[-1][1], warnings
    assert app.reports and any("Дневники:" in item for item in (app.reports[-1].get("errors") or [])), app.reports
    assert app.status == "Готово частично: доступные документы сохранены", app.status



def _assert_diary_source_buttons_route_to_expected_picker() -> None:
    source = (Path(__file__).resolve().parents[1] / "layout_sources.py").read_text(encoding="utf-8")
    start = source.index("    def _diary_compact_row")
    tail = source[start:]
    assert 'text="Тексты"' in tail and 'command=self.choose_status_file' in tail, tail[:5000]
    assert 'text="Папка"' in tail and 'command=self.choose_status_files' in tail, tail[:5000]
    assert 'text="Даты"' in tail and 'command=self.choose_diary_files' in tail, tail[:5000]


def main() -> None:
    _assert_ui_diagnosis_wins_snapshot()
    _assert_full_patient_switch_reset_matrix()
    _assert_diary_source_buttons_route_to_expected_picker()
    with TemporaryDirectory(prefix="diagnosis-override-regression-") as temp_dir:
        root = Path(temp_dir)
        _assert_all_medical_documents_receive_new_diagnosis(root)
        _assert_verbal_matching_and_word_formats(root)
        _assert_auto_refresh_and_manual_pin(root)
        _assert_manual_text_is_patient_scoped(root)
        _assert_manual_picker_accepts_doc(root)
        _assert_failed_auto_match_offers_manual_word_file(root)
        _assert_diary_failure_keeps_medical_documents(root)
        _assert_legacy_doc_parser_route(root)
    _assert_diary_creation_path_offers_manual_fallback()
    print(
        "DIAGNOSIS OVERRIDE REGRESSION OK: UI diagnosis + verbal matching + "
        "manual fallback + visible Word picker + partial-set survival + .doc/.docx source + complete patient-session reset matrix"
    )


if __name__ == "__main__":
    main()
