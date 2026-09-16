"""Regression for the real physician diary-text folder contract.

The «Тексты» folder contains Word files named by diagnosis WORDS, often in
informal Russian, and normally contains no ICD codes at all. It is a different
source type from optional numeric «Даты» 01–31.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

import diary_service
from actions_diary_flow import ActionsDiaryFlowMixin
from diary_template_selection import DiaryTemplateSelectionMixin
from diary_batch import dynamic_epicrisis_base_date, dynamic_epicrisis_dates
from diary_text_selection import (
    find_diary_text_file_for_diagnosis,
    normalize_diary_diagnosis_name,
)
from medical_models import PatientData


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Result:
    created_files: list[Path] = []
    report_path = None
    processed_files = 0
    filled_rows = 0
    month_cells_filled = 0
    final_rows_filled = 0
    removed_after_discharge_rows = 0


class _DiaryFlowHarness(ActionsDiaryFlowMixin):
    def __init__(self, text_file: Path, output_dir: Path):
        self.navigation_path_var = _Var("")
        self.patient_name_var = _Var("Тестов Тест Тестович")
        self.admission_date_var = _Var("18.05.2026")
        self.discharge_date_var = _Var("25.05.2026")
        self.diagnosis_var = _Var("F06.8 Органическое расстройство личности")
        self.status_files = [str(text_file)]
        self._diary_text_files_auto_selected = True
        self.diary_texts_dir = str(text_file.parent)
        self.diary_files: list[str] = []
        self._diary_files_auto_selected = False
        self.repeat_statuses_var = _Var(True)
        self.force_final_diary_var = _Var(True)
        self.output_dir = output_dir
        self.word_refresh_calls = 0
        self.numbered_lookup_calls = 0

    def _auto_select_diary_text_by_diagnosis(self, **_kwargs):
        self.word_refresh_calls += 1
        return True

    def _offer_manual_diary_text_file(self, **_kwargs):
        raise AssertionError("manual fallback must not open when word-matched text exists")

    def _auto_select_numbered_diary_template(self, **_kwargs):
        self.numbered_lookup_calls += 1
        raise AssertionError("numeric Dates lookup must not run for a valid Texts source")

    def _result_output_dir(self):
        return self.output_dir

    def _effective_staff_profile(self):
        return {"doctor": "Врач", "department_head": "Заведующий"}

    def _diagnostic_reports_enabled(self):
        return False

    def _log(self, _text):
        pass


class _DateLookupHarness(DiaryTemplateSelectionMixin):
    def __init__(self, text_dir: Path):
        self.diary_texts_dir = str(text_dir)
        self.lookup_calls = 0

    def _get_saved_directory(self, _key):
        return ""

    def _find_numbered_diary_template(self, _folder, _day):
        self.lookup_calls += 1
        raise AssertionError("Texts folder reached numeric 01-31 scanner")


def _assert_words_only_matching(root: Path) -> None:
    folder = root / "Тексты"
    folder.mkdir()
    organic = folder / "дневники на органичку.docx"
    schizophrenia = folder / "дневники на шизофреника.doc"
    unrelated = folder / "дневники на депрессию.docx"
    numeric = folder / "20.docx"
    for path in (organic, schizophrenia, unrelated, numeric):
        path.touch()

    # Codes and all numeric fragments disappear before comparison.
    normalized = normalize_diary_diagnosis_name("F06.8 Органическое расстройство личности 2026")
    assert "f06" not in normalized and "06" not in normalized and "2026" not in normalized, normalized
    assert "органичес" in normalized, normalized
    assert normalize_diary_diagnosis_name("F20.0") == ""

    found = find_diary_text_file_for_diagnosis(folder, "F06.8 Органическое расстройство личности")
    assert found == organic, found
    found = find_diary_text_file_for_diagnosis(folder, "F20.0 Параноидная шизофрения")
    assert found == schizophrenia, found
    assert find_diary_text_file_for_diagnosis(folder, "F20.0") is None


def _assert_selected_text_does_not_require_dates(root: Path) -> None:
    text_file = root / "дневники на органичку.docx"
    text_file.touch()
    output = root / "out"
    output.mkdir()
    app = _DiaryFlowHarness(text_file, output)
    snapshot = PatientData(
        fio="Тестов Тест Тестович",
        output_fio="Тестов Тест Тестович",
        admission_date="18.05.2026",
        discharge_date="25.05.2026",
        diagnosis="F06.8 Органическое расстройство личности",
        doctor="Врач",
        head="Заведующий",
    )

    captured: dict[str, object] = {}
    original = diary_service.DiaryService.create_text_diaries
    try:
        def fake_create(_service, **kwargs):
            captured.update(kwargs)
            return _Result()

        diary_service.DiaryService.create_text_diaries = fake_create
        app._create_diaries_impl(patient_data_snapshot=snapshot, log_created=False)
    finally:
        diary_service.DiaryService.create_text_diaries = original

    assert app.word_refresh_calls == 1, app.word_refresh_calls
    assert app.numbered_lookup_calls == 0, app.numbered_lookup_calls
    assert captured.get("status_files") == [str(text_file)], captured
    assert captured.get("diary_files") == [], captured
    assert captured.get("sick_leave_dynamic_epicrisis") is False, captured

    snapshot.expert_sick_leave_needed = "да"
    snapshot.expert_sick_leave_from = "20.05.2026"
    snapshot.birth = "01.01.1980"
    snapshot.complaints = "Жалоб активно не предъявляет"
    snapshot.treatment_plan = "Терапия по листу назначений"
    snapshot.mental_status = "Спокоен"
    captured.clear()
    try:
        diary_service.DiaryService.create_text_diaries = fake_create
        app._create_diaries_impl(patient_data_snapshot=snapshot, log_created=False)
    finally:
        diary_service.DiaryService.create_text_diaries = original
    assert captured.get("sick_leave_dynamic_epicrisis") is True, captured
    assert captured.get("sick_leave_from") == "20.05.2026", captured
    assert captured.get("birth_date") == "01.01.1980", captured
    assert captured.get("complaints") == "Жалоб активно не предъявляет", captured
    assert captured.get("treatment") == "Терапия по листу назначений", captured
    assert captured.get("profile_status") == "Спокоен", captured


def _assert_sick_leave_dynamic_epicrisis(root: Path) -> None:
    admission = date(2026, 9, 1)
    assert dynamic_epicrisis_base_date(admission, "") == admission
    assert dynamic_epicrisis_base_date(admission, "06.09.2026") == date(2026, 9, 6)
    assert dynamic_epicrisis_dates(admission, discharge_date=date(2026, 9, 28)) == (
        date(2026, 9, 11),
        date(2026, 9, 21),
    )
    # Exact legacy reference case: 20.06 is Saturday, therefore the first
    # +10 point moves to Monday 22.06; later points stay on 30.06 and 10.07.
    assert dynamic_epicrisis_dates(date(2026, 6, 10), discharge_date=date(2026, 7, 15), limit=3) == (
        date(2026, 6, 22),
        date(2026, 6, 30),
        date(2026, 7, 10),
    )
    # 19.09.2026 is Saturday: +10 from 09.09 moves to Monday 21.09.
    assert dynamic_epicrisis_dates(date(2026, 9, 9), discharge_date=date(2026, 10, 5))[0] == date(2026, 9, 21)
    # A shifted point landing on discharge is deliberately omitted.
    assert dynamic_epicrisis_dates(date(2026, 9, 6), discharge_date=date(2026, 9, 28)) == (date(2026, 9, 16),)

    text_file = root / "sick-leave-status.docx"
    status_doc = Document()
    status_doc.add_paragraph("Состояние спокойное, поведение упорядоченное.")
    status_doc.save(str(text_file))
    output = root / "sick-leave-output"
    output.mkdir()
    result = diary_service.DiaryService().create_text_diaries(
        status_files=[text_file],
        diary_files=[],
        output_dir=output,
        patient_name="Тестов Тест Тестович",
        admission_value="01.09.2026",
        discharge_value="28.09.2026",
        doctor_name="Балаганин С.В.",
        department_head_name="Можарова Е.А.",
        sick_leave_dynamic_epicrisis=True,
        sick_leave_from="01.09.2026",
        birth_date="01.01.1980",
        complaints="Жалоб активно не предъявляет",
        treatment="Терапия по листу назначений",
        profile_status="Спокоен, доступен продуктивному контакту",
    )
    generated = Document(str(result.created_files[0]))
    paragraphs = [p.text.strip() for p in generated.paragraphs if p.text.strip()]
    epicrises = [text for text in paragraphs if "Динамический эпикриз." in text]
    assert epicrises == [
        "11.09.26 Динамический эпикриз.",
        "21.09.26 Динамический эпикриз.",
    ], epicrises
    assert not any(text.startswith("28.09.26 Динамический эпикриз") for text in paragraphs), paragraphs
    assert any(text == "Лечится с: 01.09.2026." for text in paragraphs), paragraphs
    assert any(text == "Принимает: Терапия по листу назначений." for text in paragraphs), paragraphs
    # Same-date regular diary precedes the additional epicrisis and the latter
    # receives both signatures without changing regular joint-exam numbering.
    first_dynamic = paragraphs.index("11.09.26 Динамический эпикриз.")
    same_day_regular = [i for i, text in enumerate(paragraphs[:first_dynamic]) if text.startswith("11.09.26 ")]
    assert same_day_regular, paragraphs
    following = paragraphs[first_dynamic:first_dynamic + 15]
    assert any(text.startswith("Лечащий врач ") for text in following), following
    assert any(text.startswith("Зав.отделением ") for text in following), following


def _assert_fallback_output_survives_temporary_date_source(root: Path) -> None:
    text_dir = root / "persistent-text-source"
    text_dir.mkdir()
    text_file = text_dir / "дневники на органичку.docx"
    doc = Document()
    doc.add_paragraph("Состояние спокойное, поведение упорядоченное, продуктивной психопатологической симптоматики не выявляет.")
    doc.save(str(text_file))

    result = diary_service.DiaryService().create_text_diaries(
        status_files=[text_file],
        diary_files=[],
        output_dir=None,
        patient_name="Тестов Тест Тестович",
        admission_value="18.05.2026",
        discharge_value="25.05.2026",
    )

    assert result.created_files, result
    for created in result.created_files:
        assert created.exists(), f"fallback output disappeared with temporary Dates source: {created}"
        assert created.parent.resolve() == text_dir.resolve(), created
        assert ".diary-date-source-" not in str(created), created


def _assert_text_folder_never_enters_numeric_scanner(root: Path) -> None:
    text_dir = root / "Тексты"
    text_dir.mkdir(exist_ok=True)
    app = _DateLookupHarness(text_dir)
    result = app._try_find_template_in_dirs(
        [text_dir],
        [(18, "дате госпитализации", datetime(2026, 5, 18)), (19, "первому дню дневника", datetime(2026, 5, 19))],
    )
    assert result == (None, None, "", None), result
    assert app.lookup_calls == 0, app.lookup_calls


def main() -> None:
    with TemporaryDirectory(prefix="verbal-diary-source-") as temp_dir:
        root = Path(temp_dir)
        _assert_words_only_matching(root)
        _assert_selected_text_does_not_require_dates(root)
        _assert_sick_leave_dynamic_epicrisis(root)
        _assert_fallback_output_survives_temporary_date_source(root)
        _assert_text_folder_never_enters_numeric_scanner(root)
    print("VERBAL DIARY SOURCE REGRESSION OK: words-only matching; sick-leave dynamic epicrises; Texts never scanned as numeric Dates; fallback output persists")


if __name__ == "__main__":
    main()
