from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medical_expert import build_expert_anamnesis
from medical_formatting import treatment_period_text
from medical_models import PatientData, parse_sick_leave_value
from medical_parser import MedicalTextParser
from medical_service import MedicalDocumentService
import patient_registry as patient_registry_module
from patient_registry import (
    first_sick_leave_vk_date,
    hospitalization_days_on,
    has_discharge_patient_document,
    is_discharge_patient_filename,
    is_primary_patient_filename,
    next_sick_leave_vk_date,
    patient_source_candidates,
    scan_patient_registry,
    sick_leave_days_on,
)
from startup import DesktopExplorerQuadClickDetector


def _assert_sick_leave_parser() -> None:
    assert parse_sick_leave_value("да, с 01.09.2026") == ("да", "01.09.2026")
    assert parse_sick_leave_value("Да с 01092026") == ("да", "01092026")
    assert parse_sick_leave_value("с 01.09.2026") == ("да", "01.09.2026")
    assert parse_sick_leave_value("с 01.09.2026 числа") == ("да", "01.09.2026")
    assert parse_sick_leave_value("от 01092026") == ("да", "01092026")
    assert parse_sick_leave_value("нет") == ("нет", "")
    assert parse_sick_leave_value("не нужен") == ("нет", "")


def _assert_primary_text_sick_leave_label() -> None:
    data = MedicalTextParser().parse_text(
        "01.09.2026 Первичный осмотр\n"
        "Ф.И.О: Маркер Иванов Тестовый\n"
        "Год рождения: 1980\n"
        "Нужен больничный лист: да, с 20.08.2026\n"
        "Диагноз: F20.0"
    )
    assert data.sick_leave == "да, с 20.08.2026"
    assert parse_sick_leave_value(data.sick_leave) == ("да", "20.08.2026")


def _assert_primary_filename_contract() -> None:
    assert is_primary_patient_filename("Иванов первичный.docx")
    assert is_primary_patient_filename("Петров первичка.doc")
    assert is_primary_patient_filename("Сидоров (первичный).docm")
    assert not is_primary_patient_filename("Иванов выписной.docx")
    assert not is_primary_patient_filename("первичный.txt")
    assert is_discharge_patient_filename("Иванов Выписной.docx")
    assert is_discharge_patient_filename("Петров (выписной).doc")
    assert not is_discharge_patient_filename("Иванов первичный.docx")
    assert not is_discharge_patient_filename("Выписной.txt")
    assert not is_primary_patient_filename("произвольное имя.docx")

    with TemporaryDirectory(prefix="patient-discharge-name-") as temp:
        root = Path(temp)
        ivanov = root / "Иванов"
        ivanov.mkdir()
        (ivanov / "Шаблон Выписной.docx").touch()
        assert not has_discharge_patient_document(ivanov)
        (ivanov / "Иванов Выписной.docx").touch()
        assert has_discharge_patient_document(ivanov)

        renamed = root / "Петров"
        renamed.mkdir()
        arbitrary = renamed / "медицинский источник.docx"
        arbitrary.touch()
        assert patient_source_candidates(renamed) == [arbitrary]


def _assert_real_docx_registry_ingestion() -> None:
    """Exercise the exact Word -> parser -> registry path used by «Мои пациенты»."""
    with TemporaryDirectory(prefix="patient-registry-real-docx-") as temp:
        root = Path(temp)

        paragraph_folder = root / "Иванов"
        paragraph_folder.mkdir()
        paragraph_primary = paragraph_folder / "Иванов первичный.docx"
        paragraph_doc = Document()
        paragraph_doc.add_paragraph("01.10.2026")
        paragraph_doc.add_paragraph("Ф.И.О.: Маркер Иванов Тестовый")
        paragraph_doc.add_paragraph("Год рождения: 1980")
        paragraph_doc.add_paragraph("Больничный лист с 25.09.2026 числа")
        paragraph_doc.add_paragraph("Диагноз: F20.0")
        paragraph_doc.save(paragraph_primary)

        table_folder = root / "Петров"
        table_folder.mkdir()
        table_primary = table_folder / "Петров первичка.docx"
        table_doc = Document()
        table_doc.add_paragraph("02.10.2026")
        table_doc.add_paragraph("Ф.И.О.: Маркер Петров Тестовый")
        table_doc.add_paragraph("Год рождения: 1975")
        table = table_doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "Больничный лист"
        table.cell(0, 1).text = "с 20.09.2026 числа"
        table_doc.add_paragraph("Диагноз: F20.0")
        table_doc.save(table_primary)

        snapshot = scan_patient_registry(root, as_of=date(2026, 10, 2))
        assert len(snapshot.patients) == 2, snapshot.issues
        assert len(snapshot.sick_leave_patients) == 2, snapshot.issues

        by_fio = {patient.fio: patient for patient in snapshot.patients}
        ivanov = by_fio["Маркер Иванов Тестовый"]
        assert ivanov.admission_date == date(2026, 10, 1)
        assert ivanov.sick_leave_needed is True
        assert ivanov.sick_leave_from == date(2026, 9, 25)
        assert not ivanov.warning

        petrov = by_fio["Маркер Петров Тестовый"]
        assert petrov.admission_date == date(2026, 10, 2)
        assert petrov.sick_leave_needed is True
        assert petrov.sick_leave_from == date(2026, 9, 20)
        assert not petrov.warning


def _assert_registry_scan_and_independent_timelines() -> None:
    with TemporaryDirectory(prefix="patient-registry-") as temp:
        root = Path(temp)
        fixtures = {
            "Иванов": ("Иванов первичный.docx", "Маркер Иванов Тестовый", "01.09.2026", "да, с 20.08.2026"),
            "Петров": ("Петров первичка.docx", "Маркер Петров Тестовый", "15.09.2026", "нет"),
            "Сидоров": ("Сидоров первичный.docx", "Маркер Сидоров Тестовый", "20.09.2026", ""),
            "Смирнов": ("Смирнов первичный.docx", "Маркер Смирнов Тестовый", "22.09.2026", "нет"),
            "Кузнецов": ("Кузнецов первичный.docx", "Маркер Кузнецов Тестовый", "25.09.2026", "да, с 05.10.2026"),
            "Переименован": ("источник пациента.docx", "Маркер Переименован Тестовый", "27.09.2026", "нет"),
            "Ошибка": ("Ошибка первичный.docx", "", "", ""),
            "Будущий": ("Будущий первичный.docx", "Маркер Будущий Тестовый", "10.10.2026", "да, с 01.10.2026"),
            "Выписан": ("Выписан первичный.docx", "Маркер Выписан Тестовый", "05.09.2026", "да, с 05.09.2026"),
        }
        by_path = {}
        for folder_name, (filename, fio, admission, sick_leave) in fixtures.items():
            folder = root / folder_name
            folder.mkdir()
            path = folder / filename
            path.touch()
            by_path[path] = SimpleNamespace(
                fio=fio,
                admission_date=admission,
                sick_leave=sick_leave,
                expert_sick_leave_needed="",
                expert_sick_leave_from="",
            )
            if folder_name == "Выписан":
                (folder / "Выписан Выписной.docx").touch()
            if folder_name == "Смирнов":
                # A generic/example discharge file must not hide Смирнов.
                (folder / "Шаблон Выписной.docx").touch()

        no_document = root / "БезДокумента"
        no_document.mkdir()

        def parser(path: Path):
            if path.parent.name == "Ошибка":
                raise ValueError("synthetic parser failure")
            return by_path[path]

        snapshot = scan_patient_registry(root, as_of=date(2026, 10, 1), parser=parser)
        assert len(snapshot.patients) == 8, (snapshot.patients, snapshot.issues)
        assert len(snapshot.sick_leave_patients) == 1

        # Only sick leave active on the requested summary date is prioritized.
        # A future opening date stays in the ordinary group until it begins.
        assert snapshot.patients[0].fio == "Маркер Иванов Тестовый", snapshot.patients
        future_sick = next(item for item in snapshot.patients if "Кузнецов" in item.fio)
        assert future_sick.is_on_sick_leave_on(date(2026, 10, 1)) is False
        assert snapshot.patients.index(future_sick) > 0

        ivanov = next(item for item in snapshot.patients if "Иванов" in item.fio)
        assert ivanov.admission_date == date(2026, 9, 1)
        assert ivanov.sick_leave_from == date(2026, 8, 20)
        assert sick_leave_days_on(ivanov, date(2026, 10, 1)) == 43
        assert hospitalization_days_on(ivanov, date(2026, 10, 1)) == 31

        unreadable = next(item for item in snapshot.patients if item.folder.name == "Ошибка")
        assert unreadable.fio == "Ошибка"
        assert unreadable.admission_date is None
        assert hospitalization_days_on(unreadable, date(2026, 10, 1)) is None
        assert "Первичный документ не разобран" in unreadable.warning
        assert "Дата поступления не распознана" in unreadable.warning

        smirnov = next(item for item in snapshot.patients if "Смирнов" in item.fio)
        assert smirnov.admission_date == date(2026, 9, 22)

        renamed = next(item for item in snapshot.patients if "Переименован" in item.fio)
        assert renamed.primary_path is not None
        assert renamed.primary_path.name == "источник пациента.docx"

        missing_source = next(item for item in snapshot.patients if item.folder.name == "БезДокумента")
        assert missing_source.fio == "БезДокумента"
        assert missing_source.primary_path is None
        assert missing_source.admission_date is None
        assert "не найден Word-документ" in missing_source.warning


def _assert_registry_parse_cache() -> None:
    import medical_service

    original_service = medical_service.MedicalDocumentService
    patient_registry_module._PRIMARY_PARSE_CACHE.clear()

    class FakeService:
        calls = 0

        def parse_primary_document(self, path):
            type(self).calls += 1
            return SimpleNamespace(
                fio="Маркер Кеш Тестовый",
                admission_date="01.10.2026",
                sick_leave="нет",
                expert_sick_leave_needed="нет",
                expert_sick_leave_from="",
            )

    try:
        medical_service.MedicalDocumentService = FakeService
        with TemporaryDirectory(prefix="patient-registry-cache-") as temp:
            primary = Path(temp) / "Кеш первичный.docx"
            primary.write_bytes(b"first")
            first = patient_registry_module._default_parser(primary)
            second = patient_registry_module._default_parser(primary)
            assert first is second
            assert FakeService.calls == 1

            primary.write_bytes(b"changed-content")
            third = patient_registry_module._default_parser(primary)
            assert third is not second
            assert FakeService.calls == 2
    finally:
        medical_service.MedicalDocumentService = original_service
        patient_registry_module._PRIMARY_PARSE_CACHE.clear()


def _assert_explorer_quad_click_detector() -> None:
    detector = DesktopExplorerQuadClickDetector(max_gap_seconds=0.5)
    first = Path("C:/Patients/Иванов/Иванов первичный.docx")
    other = Path("C:/Patients/Петров/Петров первичный.docx")

    assert detector.observe(first, 1.0) is False
    assert detector.observe(first, 1.2) is False
    assert detector.observe(first, 1.4) is False
    assert detector.observe(first, 1.6) is True

    # A different file or a pause longer than the allowed gap must restart the
    # sequence rather than accidentally opening an unrelated patient.
    assert detector.observe(first, 3.0) is False
    assert detector.observe(other, 3.1) is False
    assert detector.observe(other, 4.0) is False
    assert detector.count == 1


def _assert_vk_wednesday_schedule() -> None:
    # Day one is exactly the date from «Нужен больничный лист с ...».
    # For every possible weekday, the first VK must be a Wednesday inside the
    # inclusive 7..15-day window, choosing the latest Wednesday that does not
    # exceed day 15.
    anchor = date(2026, 9, 1)
    for offset in range(7):
        sick_from = anchor + timedelta(days=offset)
        first = first_sick_leave_vk_date(sick_from)
        inclusive_day = (first - sick_from).days + 1
        assert first.weekday() == 2
        assert 7 <= inclusive_day <= 15
        assert first + timedelta(days=7) > sick_from + timedelta(days=14)

    sick_from = date(2026, 9, 1)
    first = first_sick_leave_vk_date(sick_from)
    assert first == date(2026, 9, 9)
    assert (first - sick_from).days + 1 == 9

    assert next_sick_leave_vk_date(sick_from, date(2026, 9, 1)) == date(2026, 9, 9)
    assert next_sick_leave_vk_date(sick_from, date(2026, 9, 9)) == date(2026, 9, 9)
    second = next_sick_leave_vk_date(sick_from, date(2026, 9, 10))
    assert second == date(2026, 9, 23)
    assert second.weekday() == 2
    assert (second - first).days + 1 == 15

    third = next_sick_leave_vk_date(sick_from, date(2026, 10, 1))
    assert third == date(2026, 10, 7)
    assert third.weekday() == 2

    # The VK document itself describes hospitalization days, not sick-leave days.
    assert treatment_period_text("01.09.2026", "09.09.2026") == (
        "Находится на лечении с 01.09.2026 (9 дней)"
    )

def _assert_discharge_stays_admission_based() -> None:
    data = PatientData(
        admission_date="10.09.2026",
        discharge_date="20.09.2026",
        expert_work_status="нет",
        expert_sick_leave_needed="да",
        expert_sick_leave_from="01.09.2026",
        expert_sick_leave_number="123456",
    )
    rendered = build_expert_anamnesis(data)
    assert "Больничный лист открыт с 01.09.2026." in rendered
    assert "Срок лечения с 10.09.2026 по 20.09.2026, 11 дней." in rendered
    assert "Срок лечения с 01.09.2026" not in rendered


def _assert_desktop_wiring_contract() -> None:
    main_source = Path("main.py").read_text(encoding="utf-8")
    startup_source = Path("startup.py").read_text(encoding="utf-8")
    mixin_source = Path("patient_registry_mixin.py").read_text(encoding="utf-8")
    window_source = Path("window_mixin.py").read_text(encoding="utf-8")
    settings_source = Path("settings_mixin.py").read_text(encoding="utf-8")

    for snippet in (
        'PATIENT_SUMMARY_ARGUMENT = "--patient-summary"',
        'PATIENT_SUMMARY_TRAY_ARGUMENT = "--patient-summary-tray"',
        "app._ensure_patient_registry_folder(first_run=True)",
        "_run_patient_summary_mode(start_in_tray=True)",
        "remove_patient_summary_autostart()",
    ):
        assert snippet in main_source
    assert "configure_patient_registry=not bool(intake_primary)" not in main_source
    for snippet in (
        "DESKTOP_DIRECT_PRIMARY_ARGUMENT",
        "_direct_primary_argument",
        "initial_direct_primary=direct_primary",
    ):
        assert snippet in main_source
    for snippet in (
        'DESKTOP_DIRECT_PRIMARY_ARGUMENT = "--open-primary"',
        "class DesktopExplorerQuadClickDetector",
        "_desktop_explorer_quad_click_loop",
        "_desktop_explorer_selected_word_file",
        "_desktop_write_direct_primary_request",
        "_desktop_take_direct_primary_request",
        "_desktop_apply_direct_primary",
        "_desktop_close_quad_click_word_document",
        "_desktop_word_document_is_open",
        "sequence_word_was_open",
        "MedicalDiaryAutofillQuadClickWordCleanup",
        'GetActiveObject("Word.Application")',
        "document.Close(SaveChanges=0)",
        "patient_registry_dir",
    ):
        assert snippet in startup_source
    for snippet in (
        'title="Из какой папки анализировать пациентов?"',
        "install_patient_summary_autostart()",
        "show_my_patients(self, *, startup_mode: bool = False, start_in_tray: bool = False)",
        "Подготовить ВК по больничному на",
        "Открыть папку пациентов",
        "Сменить путь",
        'text="× Закрыть"',
        'text="Свернуть в трей"',
        "minimize_to_tray",
        "PatientSummaryTray",
        "launch_patient_summary_tray_process",
        "open_patient_folder",
        "ordered_patients = sorted",
        "0 if item.is_on_sick_leave_on(query_date) else 1",
        "MedicalDiaryAutofillPatientRegistryScan",
        "scan_results: queue.Queue",
        'summary_var.set("Анализирую папки пациентов…")',
        "entry.primary_path is None",
    ):
        assert snippet in mixin_source
    assert 'text="Мои пациенты", command=self.show_my_patients' in window_source
    assert 'text="Папка пациентов", command=self.show_patient_registry_folder_settings' in window_source
    assert 'patient_root_button.grid(row=0, column=2' in window_source
    registry_source = Path("patient_registry.py").read_text(encoding="utf-8")
    for snippet in (
        "class PatientSummaryTray",
        "PATIENT_SUMMARY_TRAY_ARGUMENT",
        "launch_patient_summary_tray_process",
        "DETACHED_PROCESS",
        "Shell_NotifyIcon",
        "NIM_ADD",
        "NIM_DELETE",
        "consume_restore_request",
        "consume_close_request",
        "_PRIMARY_PARSE_CACHE",
        "_primary_file_signature",
        "patient_source_candidates",
        "primary_path: Path | None",
    ):
        assert snippet in registry_source
    assert "DIR_PATIENT_REGISTRY" in settings_source


def _function_source(path: str, function_name: str) -> str:
    source = Path(path).read_text(encoding="utf-8")
    marker_text = f"    def {function_name}("
    start = source.index(marker_text)
    next_def = source.find("\n    def ", start + len(marker_text))
    return source[start:] if next_def < 0 else source[start:next_def]


def _assert_sick_leave_popup_date_contract() -> None:
    popup_functions = [
        ("dialog_expert.py", "_prompt_sick_leave_start_date_if_needed"),
        ("dialog_expert.py", "_prompt_shared_clinical_options_if_needed"),
        ("dialog_expert.py", "_prompt_expert_anamnesis_details"),
        ("dialog_expert.py", "_prompt_discharge_sick_leave_number"),
        ("dialog_expert.py", "_prompt_discharge_output_requirements"),
        ("dialog_document_details.py", "_prompt_sick_leave_vk_details"),
    ]
    for path, function_name in popup_functions:
        block = _function_source(path, function_name)
        assert "С какого числа больничный лист" in block, (path, function_name)

    expert_source = Path("dialog_expert.py").read_text(encoding="utf-8")
    assert "def _store_sick_leave_start_date_value" in expert_source
    assert 'self.data.sick_leave = f"нужен с {normalized}"' in expert_source

    orchestrator_source = Path("actions_creation_orchestrator.py").read_text(encoding="utf-8")
    assert "self.expert_sick_leave_from_var.get().strip()" in orchestrator_source


def _assert_pre_admission_sick_leave_is_not_rejected() -> None:
    data = PatientData(
        fio="Маркер Иванов Тестовый",
        birth="01.01.1980",
        admission_date="10.09.2026",
        discharge_date="20.09.2026",
        case_number="1",
        diagnosis="F20.0",
        treatment_plan="Терапия",
        expert_work_status="нет",
        expert_sick_leave_needed="да",
        expert_sick_leave_from="01.09.2026",
        psych_account_status="нет",
        epi_present="нет",
        admission_occurrence="первично",
    )
    MedicalDocumentService()._validate_and_normalize_selected_data(data, ["discharge"])
    assert data.expert_sick_leave_from == "01.09.2026"
    assert data.sick_leave == "нужен с 01.09.2026"

    dialog_source = Path("dialog_expert.py").read_text(encoding="utf-8")
    assert "Дата начала больничного не может быть раньше даты госпитализации." not in dialog_source


def main() -> None:
    _assert_sick_leave_parser()
    _assert_primary_text_sick_leave_label()
    _assert_primary_filename_contract()
    _assert_real_docx_registry_ingestion()
    _assert_registry_scan_and_independent_timelines()
    _assert_registry_parse_cache()
    _assert_explorer_quad_click_detector()
    _assert_vk_wednesday_schedule()
    _assert_discharge_stays_admission_based()
    _assert_desktop_wiring_contract()
    _assert_sick_leave_popup_date_contract()
    _assert_pre_admission_sick_leave_is_not_rejected()
    print(
        "PATIENT REGISTRY REGRESSION OK: folder scan, discharged-folder exclusion, "
        "real DOCX ingestion, renamed/no-document folder census, sick-leave-first ordering, sick-leave chronology, "
        "all sick-leave popup opening dates, persistent tray, cached/asynchronous registry loading, "
        "Explorer four-click direct primary handoff, 7..15-day Wednesday VK schedule and "
        "admission-based discharge duration are locked"
    )


if __name__ == "__main__":
    main()
