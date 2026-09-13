from __future__ import annotations

import json
import tempfile
from pathlib import Path

from docx import Document

from diary_service import DiaryService
from medical_constants import DOCUMENT_ORDER
from medical_docx_reader import extract_docx_text
from medical_formatting import format_staff_instrumental_short_name, format_staff_short_name
from settings_mixin import SettingsMixin
from tools.generation_performance_profile import _make_fixture


class _SettingsHarness(SettingsMixin):
    pass


def _assert_settings(root: Path) -> None:
    settings = root / "settings.json"
    app = _SettingsHarness()
    app._settings_path = settings
    app._settings = {}
    assert app._set_staff_profile(
        doctor="Орлов Олег Олегович",
        department_head="Соколова Светлана Сергеевна",
        deputy_chief="Кузнецова Кира Константиновна",
    )
    app._set_desktop_intake_preference(False)
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["staff_profile"]["doctor"] == "Орлов Олег Олегович"
    assert payload["staff_profile"]["department_head"] == "Соколова Светлана Сергеевна"
    assert payload["staff_profile"]["deputy_chief"] == "Кузнецова Кира Константиновна"
    assert payload["desktop_intake_enabled"] is False

    restored = _SettingsHarness()
    restored._settings_path = settings
    restored._settings = restored._load_settings()
    assert restored._staff_profile_is_configured()
    assert restored._effective_staff_profile() == {
        "doctor": "Орлов Олег Олегович",
        "department_head": "Соколова Светлана Сергеевна",
        "deputy_chief": "Кузнецова Кира Константиновна",
    }
    assert restored._desktop_intake_preference() is False


def _assert_name_formatting() -> None:
    assert format_staff_short_name("Иванов Иван Иванович") == "Иванов И.И."
    assert format_staff_short_name("Можарова Е.А.") == "Можарова Е.А."
    assert format_staff_instrumental_short_name("Иванов Иван Иванович") == "Ивановым И.И."
    assert format_staff_instrumental_short_name("Петрова Анна Сергеевна") == "Петровой А.С."


def _assert_medical_documents(root: Path) -> None:
    nav, service, data = _make_fixture(root)
    data.doctor = "Орлов Олег Олегович"
    data.head = "Соколова Светлана Сергеевна"
    data.deputy_chief = "Кузнецова Кира Константиновна"
    output = root / "medical"
    created, _ = service.create_documents(
        navigation_path=nav,
        output_dir=output,
        discharge_date=data.discharge_date,
        selected_docs=DOCUMENT_ORDER,
        override_data=data,
    )
    assert len(created) == len(DOCUMENT_ORDER)
    texts = {path.name: extract_docx_text(path) for path in created}
    joined = "\n".join(texts.values())
    for stale in ("Балаганин", "Можарова", "Можаровой", "Зуйкова", "Зуйковой"):
        assert stale not in joined, f"legacy staff name leaked: {stale}"

    primary = next(text for name, text in texts.items() if "Первичный осмотр" in name)
    discharge = next(text for name, text in texts.items() if "Выписной эпикриз" in name)
    commission = next(text for name, text in texts.items() if "Совместный осмотр" in name)
    admission = next(text for name, text in texts.items() if "приёмного покоя" in name)
    assert "Первичный осмотр с зав. отд. Соколовой С.С." in primary
    assert "Врач психиатр Орлов О.О." in primary
    assert "Зав. отделением Соколова С.С." in primary
    assert "Зав. отд. Соколова С.С." in discharge and "Врач-психиатр" in discharge and "Орлов О.О." in discharge
    assert "Совместный осмотр с зам глав врача Кузнецовой К.К." in commission
    assert "Врач психиатр Орлов О.О." in admission


def _assert_diaries(root: Path) -> None:
    statuses = root / "statuses.docx"
    status_doc = Document()
    status_doc.add_paragraph("Состояние стабильное, контакт доступен, лечение переносит удовлетворительно.")
    status_doc.save(statuses)

    dates = root / "dates.docx"
    dates_doc = Document()
    table = dates_doc.add_table(rows=1, cols=4)
    for index, title in enumerate(("День госпитализации", "Число", "Месяц/Год", "Дневник наблюдения")):
        table.rows[0].cells[index].text = title
    for hospital_day in (1, 2, 3, 4):
        row = table.add_row()
        row.cells[0].text = str(hospital_day)
    dates_doc.save(dates)

    result = DiaryService().create_text_diaries(
        status_files=[statuses],
        diary_files=[dates],
        output_dir=root / "diaries",
        patient_name="Иванова Ирина Ивановна",
        gender_source_name="Иванова Ирина Ивановна",
        admission_value="10.06.2026",
        discharge_value="13.06.2026",
        doctor_name="Орлов Олег Олегович",
        department_head_name="Соколова Светлана Сергеевна",
    )
    assert len(result.created_files) == 1
    text = extract_docx_text(result.created_files[0])
    assert "Лечащий врач Орлов О.О." in text
    assert "Зав.отделением Соколова С.С." in text
    assert "Балаганин" not in text and "Можарова" not in text


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="staff-profile-regression-") as tmp:
        root = Path(tmp)
        _assert_name_formatting()
        _assert_settings(root)
        _assert_medical_documents(root)
        _assert_diaries(root)
    print("STAFF PROFILE REGRESSION OK: settings + 7 medical documents + production diary")


if __name__ == "__main__":
    main()
