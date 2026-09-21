"""Headless contract checks for the optional desktop patient-folder workflow."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import startup
import main as app_main
import medical_docx_blocks
from medical_service import MedicalDocumentService
from settings_mixin import SettingsMixin


def _assert_naming_contract() -> None:
    name = startup.desktop_build_patient_folder_name(
        fio="Иванов Иван Иванович",
        admission_date=date(2026, 5, 12),
        fallback_stem="Первичный осмотр",
    )
    assert name == "Иванов И.И. май 2026", name

    custom = startup.desktop_build_patient_folder_name(
        fio="Петров Пётр Петрович",
        admission_date="03.09.2026",
        discharge_date="19.09.2026",
        fallback_stem="patient",
        settings={"parts": ["full_fio", "admission_discharge_dates"], "date_format": "short"},
    )
    assert custom == "Петров Пётр Петрович 03.09.26 — 19.09.26", custom


def _assert_folder_naming_settings_persist_without_patient_data() -> None:
    class SettingsHarness(SettingsMixin):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        settings_path = Path(tmp) / "settings.json"
        app = SettingsHarness()
        app._settings_path = settings_path
        app._settings = {}
        app._set_patient_folder_naming_settings(
            parts=["full_fio", "discharge_date"],
            date_format="full",
        )
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        assert payload["patient_folder_naming"] == {
            "parts": ["full_fio", "discharge_date"],
            "date_format": "full",
        }, payload
        serialized = settings_path.read_text(encoding="utf-8")
        assert "Иванов" not in serialized and "F20.0" not in serialized

        restored = SettingsHarness()
        restored._settings_path = settings_path
        restored._settings = restored._load_settings()
        assert restored._patient_folder_naming_settings() == {
            "parts": ["full_fio", "discharge_date"],
            "date_format": "full",
        }


def _assert_intake_uses_saved_folder_naming() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "patient.docx"
        source.write_bytes(b"fixture")
        captured: list[dict | None] = []

        class Root:
            def deiconify(self): pass
            def lift(self): pass
            def focus_force(self): pass

        class App:
            root = Root()
            def _patient_folder_naming_settings(self):
                return {"parts": ["full_fio", "discharge_date"], "date_format": "full"}
            def _apply_primary_document_path(self, path, prompt_for_referral=True):
                self.applied = (path, prompt_for_referral)

        original_quiet = startup.desktop_intake_file_is_quiet
        original_classifier = startup.desktop_intake_is_primary_document
        original_prepare = startup.desktop_intake_prepare_patient_folder
        try:
            startup.desktop_intake_file_is_quiet = lambda _path: True  # type: ignore[assignment]
            startup.desktop_intake_is_primary_document = lambda _path: True  # type: ignore[assignment]
            def fake_prepare(path, **kwargs):
                captured.append(kwargs.get("folder_settings"))
                return Path(path)
            startup.desktop_intake_prepare_patient_folder = fake_prepare  # type: ignore[assignment]
            app = App()
            assert startup._desktop_process_primary(app, source)
            assert captured == [
                {"parts": ["full_fio", "discharge_date"], "date_format": "full"}
            ], captured
            assert app.applied == (str(source), True)
        finally:
            startup.desktop_intake_file_is_quiet = original_quiet  # type: ignore[assignment]
            startup.desktop_intake_is_primary_document = original_classifier  # type: ignore[assignment]
            startup.desktop_intake_prepare_patient_folder = original_prepare  # type: ignore[assignment]


def _assert_primary_detection_contract() -> None:
    primary = """
    12.05.2026 Первичный осмотр
    История болезни № 123
    Ф.И.О. Иванов Иван Иванович
    Жалобы при поступлении
    Психический статус
    Диагноз
    План лечения
    """
    referral = """
    12.05.2026 Направление на госпитализацию
    ФИО Иванов Иван Иванович
    Диагноз F20.0
    """
    discharge = """
    Выписной эпикриз
    История болезни № 123
    Ф.И.О. Иванов Иван Иванович
    Диагноз F20.0
    Лечение
    """
    assert startup.desktop_intake_primary_score(primary) >= 5
    assert startup.desktop_intake_primary_score(referral) >= 5
    assert startup.desktop_intake_primary_score(discharge) >= 5
    assert startup.desktop_intake_is_candidate_word_file("Первичный.doc")
    assert startup.desktop_intake_is_candidate_word_file("Первичный.docx")
    assert startup.desktop_intake_is_candidate_word_file("Первичный.docm")
    assert not startup.desktop_intake_is_candidate_word_file("~$Первичный.docx")
    assert not startup.desktop_intake_is_candidate_word_file("ЭПИ.pdf")



def _assert_canonical_primary_parser_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical = root / "patient.docx"
        doc = Document()
        doc.add_paragraph("12.05.2026 Первичный осмотр")
        doc.add_paragraph("Ф.И.О.: Иванов Иван Иванович")
        doc.add_paragraph("Дата рождения: 01.01.1980")
        doc.add_paragraph("В 3 отделение КДП поступает первично")
        doc.add_paragraph("Анамнез жизни: без особенностей")
        doc.add_paragraph("Психический статус: контактен")
        doc.add_paragraph("Диагноз: F20.0")
        doc.save(canonical)
        canonical_data = MedicalDocumentService().parse_primary_document(canonical)
        assert startup.desktop_intake_is_primary_document(canonical), "canonical parser primary was rejected"

        # DOCM uses the same OOXML reader path and must remain first-class input.
        macro = root / "patient.docm"
        shutil.copyfile(canonical, macro)
        macro_data = MedicalDocumentService().parse_primary_document(macro)
        assert macro_data.fio == "Иванов Иван Иванович", macro_data.fio
        assert startup.desktop_intake_is_primary_document(macro), "DOCM primary was rejected"

        # Real binary DOC conversion requires Microsoft Word and is therefore
        # exercised on Windows through the same converter. Here we replace only
        # the external COM conversion with a deterministic copy so the contract
        # proves every caller routes .doc through the shared conversion boundary.
        legacy = root / "patient.doc"
        legacy.write_bytes(b"legacy-doc-placeholder")
        original_converter = medical_docx_blocks.convert_legacy_doc_to_docx
        conversion_calls: list[tuple[Path, Path]] = []
        try:
            def fake_converter(source: Path, target: Path) -> None:
                conversion_calls.append((Path(source), Path(target)))
                shutil.copyfile(canonical, target)

            medical_docx_blocks.convert_legacy_doc_to_docx = fake_converter
            legacy_data = MedicalDocumentService().parse_primary_document(legacy)
            assert legacy_data.fio == canonical_data.fio == "Иванов Иван Иванович", legacy_data.fio
            assert legacy_data.admission_date == canonical_data.admission_date
            assert legacy_data.diagnosis == canonical_data.diagnosis
            assert legacy_data.input_document_kind == canonical_data.input_document_kind
            assert len(conversion_calls) == 1, conversion_calls
            assert conversion_calls[0][0].samefile(legacy), conversion_calls
            assert conversion_calls[0][1].suffix.lower() == ".docx"
            conversion_calls.clear()
            assert startup.desktop_intake_is_primary_document(legacy), "DOC primary was rejected"
            assert conversion_calls == [], "same .doc revision was converted more than once"
            legacy.write_bytes(b"legacy-doc-placeholder-updated")
            assert startup.desktop_intake_is_primary_document(legacy), "updated DOC primary was rejected"
            assert len(conversion_calls) == 1, conversion_calls
        finally:
            medical_docx_blocks.convert_legacy_doc_to_docx = original_converter

        discharge = root / "discharge.docx"
        doc = Document()
        doc.add_paragraph("15.05.2026 Выписной эпикриз № 123")
        doc.add_paragraph("Ф.И.О.: Иванов Иван Иванович")
        doc.add_paragraph("Дата рождения: 01.01.1980")
        doc.add_paragraph("Находился на лечении в стационаре с 12.05.2026 по 15.05.2026")
        doc.add_paragraph("Диагноз: F20.0")
        doc.add_paragraph("Лечение: терапия")
        doc.save(discharge)
        assert startup.desktop_intake_is_primary_document(discharge), "discharge source was rejected"

        discharge_info = startup._desktop_patient_folder_info(
            discharge,
            settings={"parts": ["full_fio", "discharge_date"], "date_format": "full"},
        )
        assert discharge_info.admission_date == "12.05.2026", discharge_info
        assert discharge_info.discharge_date == "15.05.2026", discharge_info
        assert discharge_info.folder_name == "Иванов Иван Иванович 15.05.2026", discharge_info.folder_name

        universal_sources = (
            ("Осмотр врача приёмного покоя.docx", "12.05.2026 Осмотр врача приёмного покоя."),
            ("Совместный осмотр.docx", "18.05.2026 Совместный осмотр с зам глав врача № 2"),
            ("Пациент ВК на МСЭ.docx", "ВК на МСЭ"),
            ("Пациент ВК больничный.docx", "ВК больничный"),
            ("Пациент Акт для РВК.docx", "О СОСТОЯНИИ ЗДОРОВЬЯ ГРАЖДАНИНА № 7"),
        )
        for filename, title in universal_sources:
            source = root / filename
            doc = Document()
            doc.add_paragraph(title)
            doc.add_paragraph("Ф.И.О.: Иванов Иван Иванович")
            doc.add_paragraph("Дата рождения: 01.01.1980")
            doc.add_paragraph("Диагноз: F20.0")
            doc.add_paragraph("Лечение: терапия")
            if "РВК" in filename:
                doc.add_paragraph("Госпитализируется по направлению военного комиссариата Ленинского района.")
            doc.save(source)
            assert startup.desktop_intake_is_primary_document(source), f"universal source was rejected: {filename}"

        epi_only = root / "ЭПИ.docx"
        doc = Document()
        doc.add_paragraph("ЭПИ: тестовая информация")
        doc.save(epi_only)
        assert not startup.desktop_intake_is_primary_document(epi_only), "standalone EPI must not become patient source"

        diary_only = root / "Дневник наблюдения.docx"
        doc = Document()
        doc.add_paragraph("Дневник наблюдения")
        doc.add_paragraph("Психический статус: без особенностей")
        doc.save(diary_only)
        assert not startup.desktop_intake_is_primary_document(diary_only), "diary must stay outside patient-source intake"


def _assert_closed_gui_wake_is_classification_free() -> None:
    """A closed GUI must wake for supported Word input before medical parsing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        candidate = root / "real-world-primary.docx"
        candidate.write_bytes(b"not-parsed-by-hidden-watcher")

        original_quiet = startup.desktop_intake_file_is_quiet
        original_classifier = startup.desktop_intake_is_primary_document
        try:
            startup.desktop_intake_file_is_quiet = lambda _path: True  # type: ignore[assignment]

            def forbidden_classifier(_path):
                raise AssertionError("hidden watcher must not medically classify before GUI launch")

            startup.desktop_intake_is_primary_document = forbidden_classifier  # type: ignore[assignment]
            wake = startup.desktop_intake_scan_wake_candidates(root)
            assert wake == [candidate], wake
        finally:
            startup.desktop_intake_is_primary_document = original_classifier  # type: ignore[assignment]
            startup.desktop_intake_file_is_quiet = original_quiet  # type: ignore[assignment]

    agent_source = Path(startup.__file__).read_text(encoding="utf-8")
    start = agent_source.index("def run_desktop_intake_agent")
    end = agent_source.index("# Existing-GUI handoff", start)
    agent_body = agent_source[start:end]
    assert "_desktop_candidate_snapshot(root)" in agent_body
    assert "desktop_intake_scan_primary_candidates(root)" not in agent_body
    assert "recently_launched" not in agent_body


def _assert_legacy_word_conversion_never_quits_user_word() -> None:
    """COM conversion may close its own Word instance, never the doctor's."""
    if medical_docx_blocks.os.name != "nt":
        return

    original_pythoncom = sys.modules.get("pythoncom")
    original_win32com = sys.modules.get("win32com")
    original_client = sys.modules.get("win32com.client")

    class FakeOpened:
        def __init__(self) -> None:
            self.closed = 0

        def SaveAs2(self, target, **_kwargs) -> None:
            Path(target).write_bytes(b"fake-docx")

        def Close(self, _save) -> None:
            self.closed += 1

    class FakeDocuments:
        def __init__(self, opened) -> None:
            self.opened = opened

        def Open(self, *_args, **_kwargs):
            return self.opened

    class FakeWord:
        def __init__(self, hwnd: int, *, user_control: bool) -> None:
            self.Hwnd = hwnd
            self.UserControl = user_control
            self.Visible = True
            self.DisplayAlerts = 1
            self.opened = FakeOpened()
            self.Documents = FakeDocuments(self.opened)
            self.quit_calls = 0

        def Quit(self) -> None:
            self.quit_calls += 1

    pythoncom = ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None  # type: ignore[attr-defined]
    pythoncom.CoUninitialize = lambda: None  # type: ignore[attr-defined]
    package = ModuleType("win32com")
    package.__path__ = []  # type: ignore[attr-defined]
    client = ModuleType("win32com.client")
    package.client = client  # type: ignore[attr-defined]

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.doc"
        source.write_bytes(b"legacy")

        user_word = FakeWord(101, user_control=True)
        client.GetActiveObject = lambda _name: user_word  # type: ignore[attr-defined]
        client.DispatchEx = lambda _name: user_word  # type: ignore[attr-defined]

        sys.modules["pythoncom"] = pythoncom
        sys.modules["win32com"] = package
        sys.modules["win32com.client"] = client
        try:
            target = Path(tmp) / "same-user.docx"
            medical_docx_blocks.convert_legacy_doc_to_docx(source, target)
            assert target.is_file()
            assert user_word.opened.closed == 1
            assert user_word.quit_calls == 0, "existing user Word was terminated"

            automation_word = FakeWord(202, user_control=False)

            def no_active_word(_name):
                raise RuntimeError("no active Word")

            client.GetActiveObject = no_active_word  # type: ignore[attr-defined]
            client.DispatchEx = lambda _name: automation_word  # type: ignore[attr-defined]
            target2 = Path(tmp) / "owned-automation.docx"
            medical_docx_blocks.convert_legacy_doc_to_docx(source, target2)
            assert automation_word.opened.closed == 1
            assert automation_word.quit_calls == 1, "owned automation Word was leaked"
        finally:
            if original_pythoncom is None:
                sys.modules.pop("pythoncom", None)
            else:
                sys.modules["pythoncom"] = original_pythoncom
            if original_win32com is None:
                sys.modules.pop("win32com", None)
            else:
                sys.modules["win32com"] = original_win32com
            if original_client is None:
                sys.modules.pop("win32com.client", None)
            else:
                sys.modules["win32com.client"] = original_client


def _assert_agent_heartbeat_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        original_runtime_dir = startup._desktop_runtime_dir
        try:
            startup._desktop_runtime_dir = lambda: runtime  # type: ignore[assignment]
            assert startup._desktop_agent_is_active() is False
            startup._desktop_touch_agent_heartbeat()
            assert startup._desktop_agent_is_active() is True
            heartbeat = runtime / "desktop-intake-agent.heartbeat"
            heartbeat.write_text(
                '{"schema": 1, "timestamp": %s, "identity": "%s"}'
                % (time.time() - 60, startup._desktop_current_agent_identity()),
                encoding="ascii",
            )
            assert startup._desktop_agent_is_active() is False
        finally:
            startup._desktop_runtime_dir = original_runtime_dir  # type: ignore[assignment]

def _assert_top_level_only_and_safe_move() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "Выписанные пациенты"
        root.mkdir()
        nested = root / "Старый пациент"
        nested.mkdir()
        (nested / "Первичный.docx").write_bytes(b"nested")
        top = root / "Первичный.docx"
        top.write_bytes(b"same-primary")

        candidates = startup.desktop_intake_iter_candidates(root)
        assert candidates == (top,), candidates

        moved = startup.desktop_intake_prepare_patient_folder(
            top,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert moved.parent.name == "Иванов И.И. май 2026"
        assert moved.read_bytes() == b"same-primary"
        assert not top.exists()

        duplicate = root / "Первичный.docx"
        duplicate.write_bytes(b"same-primary")
        reused = startup.desktop_intake_prepare_patient_folder(
            duplicate,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert reused == moved
        assert not duplicate.exists()

        changed = root / "Первичный исправленный.docx"
        changed.write_bytes(b"changed-primary")
        second = startup.desktop_intake_prepare_patient_folder(
            changed,
            intake_root=root,
            folder_name="Иванов И.И. май 2026",
        )
        assert second.parent.name == "Иванов И.И. май 2026 (2)"
        assert second.read_bytes() == b"changed-primary"


def _assert_agent_update_and_encoding_contract() -> None:
    payload = startup.desktop_intake_startup_vbs_payload(
        [r"C:\Программа\MedicalDiaryAutofill.exe", startup.DESKTOP_INTAKE_AGENT_ARGUMENT]
    )
    encoded = payload.encode("utf-16")
    assert encoded.startswith(b"\xff\xfe")
    assert not encoded.startswith(b"\xef\xbb\xbf")
    assert payload.splitlines()[0] == "On Error Resume Next"
    assert "WScript.Shell" in payload
    assert "shell.Run" in payload

    with tempfile.TemporaryDirectory() as tmp:
        runtime = Path(tmp)
        current = runtime / "new" / "MedicalDiaryAutofill.exe"
        current.parent.mkdir()
        current.write_bytes(b"current-build")
        old = runtime / "old" / "MedicalDiaryAutofill.exe"
        old.parent.mkdir()
        old.write_bytes(b"old-build")

        original_runtime_dir = startup._desktop_runtime_dir
        original_native_command = startup._desktop_native_gui_command
        original_identity_cache = startup._DESKTOP_AGENT_IDENTITY_CACHE
        try:
            startup._desktop_runtime_dir = lambda: runtime  # type: ignore[assignment]

            current_command = [str(current)]
            current_identity = startup._desktop_build_agent_identity(current_command)
            startup._desktop_native_gui_command = lambda: current_command  # type: ignore[assignment]
            startup._DESKTOP_AGENT_IDENTITY_CACHE = current_identity
            startup._desktop_write_agent_handoff()
            assert startup._desktop_agent_is_retired() is False
            assert startup._desktop_launch_command() == current_command

            old_command = [str(old)]
            old_identity = startup._desktop_build_agent_identity(old_command)
            assert old_identity != current_identity
            startup._desktop_native_gui_command = lambda: old_command  # type: ignore[assignment]
            startup._DESKTOP_AGENT_IDENTITY_CACHE = old_identity
            assert startup._desktop_agent_is_retired() is True
            assert startup._desktop_launch_command() == current_command
        finally:
            startup._DESKTOP_AGENT_IDENTITY_CACHE = original_identity_cache
            startup._desktop_runtime_dir = original_runtime_dir  # type: ignore[assignment]
            startup._desktop_native_gui_command = original_native_command  # type: ignore[assignment]



def _assert_stale_disabled_intake_self_heals() -> None:
    class FakeApp:
        def __init__(self) -> None:
            self.root = object()
            self._desktop_intake_enabled_for_session = False
            self.preference = False

        def _desktop_intake_preference(self):
            return self.preference

        def _set_desktop_intake_preference(self, enabled: bool) -> None:
            self.preference = bool(enabled)

        def _staff_profile_is_configured(self) -> bool:
            return True

        def _prompt_staff_profile(self, *, first_run: bool = False) -> bool:
            raise AssertionError("staff prompt must not run in this contract probe")

    with tempfile.TemporaryDirectory() as tmp:
        intake_root = Path(tmp) / "Desktop" / "Выписанные пациенты"
        marker_path = Path(tmp) / "no-onboarding-marker.flag"
        original_root = app_main.desktop_intake_root_path
        original_marker = app_main._installation_onboarding_marker_path
        original_os = app_main.os
        try:
            # Exercise the Windows-only onboarding branch even when this
            # headless contract is invoked from a non-Windows developer host.
            app_main.os = SimpleNamespace(name="nt", environ={})  # type: ignore[assignment]
            app_main.desktop_intake_root_path = lambda: intake_root  # type: ignore[assignment]
            app_main._installation_onboarding_marker_path = lambda: marker_path  # type: ignore[assignment]
            app = FakeApp()
            app_main._first_launch_onboarding(app)
            assert intake_root.is_dir(), "mandatory intake root was not recreated"
            assert app._desktop_intake_enabled_for_session is True
            assert app.preference is True, "legacy desktop_intake_enabled=false was not healed"
        finally:
            app_main.os = original_os  # type: ignore[assignment]
            app_main.desktop_intake_root_path = original_root  # type: ignore[assignment]
            app_main._installation_onboarding_marker_path = original_marker  # type: ignore[assignment]

    if startup.os.name != "nt":
        return

    class FakeRoot:
        def __init__(self) -> None:
            self.scheduled: list[int] = []

        def winfo_exists(self) -> bool:
            return True

        def after(self, delay: int, callback) -> None:
            self.scheduled.append(delay)

    class RuntimeApp:
        def __init__(self) -> None:
            self.root = FakeRoot()
            self._desktop_intake_enabled_for_session = False

    calls: list[str] = []
    originals = {
        "touch": startup._desktop_touch_gui_heartbeat,
        "ensure": startup.desktop_intake_ensure_root,
        "startup": startup._desktop_install_agent_autostart,
        "run_key": startup._desktop_install_agent_run_key,
        "start": startup._desktop_start_agent_process,
        "heartbeat": startup._desktop_schedule_heartbeat,
    }
    with tempfile.TemporaryDirectory() as tmp:
        try:
            startup._desktop_touch_gui_heartbeat = lambda: calls.append("touch")  # type: ignore[assignment]
            startup.desktop_intake_ensure_root = lambda: Path(tmp)  # type: ignore[assignment]
            startup._desktop_install_agent_autostart = lambda: calls.append("startup") or True  # type: ignore[assignment]
            startup._desktop_install_agent_run_key = lambda: calls.append("run_key") or True  # type: ignore[assignment]
            startup._desktop_start_agent_process = lambda: calls.append("start") or True  # type: ignore[assignment]
            startup._desktop_schedule_heartbeat = lambda app: calls.append("heartbeat")  # type: ignore[assignment]
            app = RuntimeApp()
            startup.start_desktop_intake_runtime(app)
            assert {"touch", "startup", "run_key", "start", "heartbeat"} <= set(calls), calls
            assert app.root.scheduled, "runtime health/poll callbacks were not scheduled"
        finally:
            startup._desktop_touch_gui_heartbeat = originals["touch"]  # type: ignore[assignment]
            startup.desktop_intake_ensure_root = originals["ensure"]  # type: ignore[assignment]
            startup._desktop_install_agent_autostart = originals["startup"]  # type: ignore[assignment]
            startup._desktop_install_agent_run_key = originals["run_key"]  # type: ignore[assignment]
            startup._desktop_start_agent_process = originals["start"]  # type: ignore[assignment]
            startup._desktop_schedule_heartbeat = originals["heartbeat"]  # type: ignore[assignment]


def main() -> None:
    _assert_naming_contract()
    _assert_folder_naming_settings_persist_without_patient_data()
    _assert_intake_uses_saved_folder_naming()
    _assert_primary_detection_contract()
    _assert_canonical_primary_parser_contract()
    _assert_top_level_only_and_safe_move()
    _assert_agent_update_and_encoding_contract()
    _assert_closed_gui_wake_is_classification_free()
    _assert_legacy_word_conversion_never_quits_user_word()
    _assert_agent_heartbeat_contract()
    _assert_stale_disabled_intake_self_heals()
    print("desktop intake contract: PASS")


if __name__ == "__main__":
    main()
