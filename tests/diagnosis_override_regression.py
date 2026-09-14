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
from actions_medical_flow import ActionsMedicalFlowMixin
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
    # Every current document kind owns a diagnosis placement; assert the new
    # verbal diagnosis is present in each generated file rather than merely once.
    for name, text in texts.items():
        assert "Параноидная шизофрения" in text, f"new UI diagnosis missing from {name}"


def _assert_verbal_matching_and_word_formats(root: Path) -> None:
    folder = root / "Тексты"
    folder.mkdir()
    # The ICD-looking filename deliberately points to the wrong verbal meaning.
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

    # Code-only input must not steer semantic diary selection.
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

    # If the new diagnosis has no candidate, the stale automatic file must be
    # cleared instead of silently surviving from the previous diagnosis.
    assert not app._auto_select_diary_text_by_diagnosis(
        diagnosis_override="Кататоническое состояние редкого типа",
        ask_folder=False,
    )
    assert app.status_files == [], app.status_files

    # Manual choice is sticky and must not be replaced by diagnosis automation.
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

    # Before the first primary document is loaded, an intentionally preselected
    # text source is allowed to remain available for that first patient.
    app.status_files = [str(manual_file)]
    app._diary_text_files_auto_selected = False
    app._reset_primary_document_runtime_state(clear_patient_inputs=False)
    assert app.status_files == [str(manual_file)], app.status_files
    assert app._diary_text_files_auto_selected is False

    # A real primary-document switch is a patient boundary. Manual text chosen
    # for patient A must never leak into patient B; only reusable folder memory
    # may survive so the new diagnosis can be selected afresh.
    app.status_files = [str(manual_file)]
    app._diary_text_files_auto_selected = False
    app._reset_primary_document_runtime_state(clear_patient_inputs=True)
    assert app.status_files == [], app.status_files
    assert app._diary_text_files_auto_selected is False


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
    assert "*.doc *.docx *.docm" in repr(captured.get("filetypes"))


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

    # The batch boundary must also admit .doc for text sources while keeping
    # calendar templates on OOXML only.
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


def main() -> None:
    _assert_ui_diagnosis_wins_snapshot()
    with TemporaryDirectory(prefix="diagnosis-override-regression-") as temp_dir:
        root = Path(temp_dir)
        _assert_all_medical_documents_receive_new_diagnosis(root)
        _assert_verbal_matching_and_word_formats(root)
        _assert_auto_refresh_and_manual_pin(root)
        _assert_manual_text_is_patient_scoped(root)
        _assert_manual_picker_accepts_doc(root)
        _assert_legacy_doc_parser_route(root)
    print(
        "DIAGNOSIS OVERRIDE REGRESSION OK: UI diagnosis + verbal matching + "
        "manual .doc/.docx source + patient-scoped override"
    )


if __name__ == "__main__":
    main()
