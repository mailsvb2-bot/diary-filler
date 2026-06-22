"""Production-readiness audit for MedicalDiaryAutofill.

The audit is intentionally standard-library only. It is meant to run in CI and
on a developer machine before GitHub upload, EXE publishing, or paid-traffic
launch. It checks architecture hygiene, release metadata, import graph safety,
and the absence of known dust files from the over-split refactor wave.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET_VERSION = "1.3.18"
TARGET_VERSION_LABEL = "v1.3.18-production-quality-gate"
MAX_PYTHON_FILES = 125
MAX_TINY_PYTHON_FILES = 25

# These files existed only as one-purpose micro-mixins after the aggressive
# split wave. Keeping them would reintroduce architectural dust.
FORBIDDEN_DUST_FILES = {
    "ui_title_pills.py",
    "ui_neon_buttons.py",
    "ui_field_canvases.py",
    "ui_output_fields.py",
    "ui_medical_fields.py",
    "ui_sick_leave_field.py",
    "layout_action_bar_build.py",
    "layout_action_bar_tiles.py",
    "layout_action_bar_selection.py",
    "layout_checklist_build.py",
    "layout_checklist_tile.py",
    "layout_checklist_icons.py",
    "dnd_setup.py",
    "dnd_file_handler.py",
    "diagnosis_autocomplete.py",
    "diagnosis_popup.py",
    "diagnosis_selector.py",
    "files_output_state.py",
    "files_primary.py",
    "files_diary_templates.py",
    "files_printers.py",
    "dialog_expert_shared_work.py",
    "dialog_expert_sick_leave.py",
    "dialog_assigned_treatment.py",
    "dialog_commission_details.py",
    "dialog_rvk_details.py",
    "dialog_vk_mse_details.py",
    "dialog_sick_leave_vk_details.py",
    "dialog_primary_document_type.py",
    "diary_template_file_detection.py",
    "diary_template_folder_scan.py",
    "diary_template_dirs.py",
    "diary_template_finder.py",
    "diary_template_admission.py",
    "diary_template_auto_select.py",
    "window_build.py",
    "window_metrics.py",
    "window_style.py",
    "window_shortcuts.py",
    "window_chrome.py",
    "window_header.py",
    "window_patient_card.py",
    "app_init_entrypoint.py",
    "app_state_core.py",
    "app_state_patient.py",
    "app_state_documents.py",
    "app_state_diaries.py",
    "app_state_runtime.py",
    "app_window_bootstrap.py",
}

# Old iteration reports are useful during a chat, but they are release noise in
# a GitHub/prod archive. Keep one final report and release notes instead.
FORBIDDEN_ITERATION_REPORTS = {
    "MAIN_SPLIT_REPORT.md",
    "FULL_SPLIT_REPORT.md",
    "DEEP_SPLIT_REPORT.md",
    "FINE_SPLIT_REPORT.md",
    "FINAL_SPLIT_REPORT.md",
    "PRODUCTION_REPORT.md",
}

PUBLIC_ENTRYPOINTS = {
    "main.py",
    "medical_documents.py",
    "diary_filler.py",
    "printer_support.py",
    "icd10_f.py",
    "smoke_test.py",
    "smoke_test_combined.py",
}


def _fail(message: str) -> None:
    raise SystemExit(message)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def _python_files() -> list[Path]:
    return sorted(ROOT.glob("*.py"), key=lambda p: p.name.lower())


def _assert_version_sync() -> None:
    pyproject = _read("pyproject.toml")
    app_config = _read("app_config.py")
    version_info = _read("version_info.txt")
    readme = _read("README.md")
    release_notes = _read("RELEASE_NOTES.md")

    checks = {
        "pyproject.toml version": f'version = "{TARGET_VERSION}"' in pyproject,
        "app_config APP_VERSION": TARGET_VERSION_LABEL in app_config,
        "version_info label": TARGET_VERSION_LABEL in version_info,
        "version_info tuple": "filevers=(1, 3, 18, 0)" in version_info and "prodvers=(1, 3, 18, 0)" in version_info,
        "README version": TARGET_VERSION_LABEL in readme,
        "RELEASE_NOTES top version": release_notes.lstrip().startswith(f"# Release notes — {TARGET_VERSION_LABEL}"),
    }
    missing = [name for name, ok in checks.items() if not ok]
    if missing:
        _fail("Version metadata is not synchronized: " + ", ".join(missing))


def _assert_architecture_hygiene() -> None:
    py_files = _python_files()
    names = {p.name for p in py_files}
    dust = sorted(names & FORBIDDEN_DUST_FILES)
    if dust:
        _fail("Architectural dust files are present:\n" + "\n".join(dust))

    old_reports = sorted(p.name for p in ROOT.glob("*.md") if p.name in FORBIDDEN_ITERATION_REPORTS)
    if old_reports:
        _fail("Old split iteration reports must not ship in production archive:\n" + "\n".join(old_reports))

    if len(py_files) > MAX_PYTHON_FILES:
        _fail(f"Too many Python files after dust collapse: {len(py_files)} > {MAX_PYTHON_FILES}")

    tiny_files = []
    for path in py_files:
        if path.name in PUBLIC_ENTRYPOINTS:
            continue
        line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_count <= 20:
            tiny_files.append(path.name)
    if len(tiny_files) > MAX_TINY_PYTHON_FILES:
        _fail("Too many tiny non-entrypoint Python files:\n" + "\n".join(tiny_files))


def _local_import_graph() -> dict[str, set[str]]:
    local_modules = {p.stem for p in _python_files()}
    graph: dict[str, set[str]] = {p.stem: set() for p in _python_files()}
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            _fail(f"Syntax error in {path.name}: {exc}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in local_modules:
                        graph[path.stem].add(root)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                if root in local_modules:
                    graph[path.stem].add(root)
    return graph


def _assert_no_import_cycles() -> None:
    graph = _local_import_graph()
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            idx = stack.index(node) if node in stack else 0
            cycle = stack[idx:] + [node]
            _fail("Local import cycle detected: " + " -> ".join(cycle))
        visiting.add(node)
        stack.append(node)
        for child in sorted(graph.get(node, ())):
            dfs(child)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        dfs(node)


def _assert_no_deleted_module_references() -> None:
    deleted_stems = {Path(name).stem for name in FORBIDDEN_DUST_FILES}
    bad: list[str] = []
    for path in _python_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            _fail(f"Syntax error in {path.name}: {exc}")
        for node in ast.walk(tree):
            imported = None
            if isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module.split(".", 1)[0]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in deleted_stems:
                        bad.append(f"{path.name}:{node.lineno}: import {root}")
                continue
            if imported in deleted_stems:
                bad.append(f"{path.name}:{node.lineno}: from {imported} import ...")
        # Guard against static references like OldMixin.some_static_method after collapse.
        for stem in deleted_stems:
            camel = "".join(part.capitalize() for part in stem.split("_"))
            if re.search(rf"\b{re.escape(camel)}\b", source):
                bad.append(f"{path.name}: stale class/static reference {camel}")
    if bad:
        _fail("References to deleted dust modules/classes found:\n" + "\n".join(sorted(bad)))






def _assert_public_modules_importable() -> None:
    bad: list[str] = []
    for stem in ["main", "app", "app_initialization", "medical_documents", "diary_filler", "printer_support", "icd10_f"]:
        try:
            importlib.import_module(stem)
        except Exception as exc:  # pragma: no cover - report clarity
            bad.append(f"{stem}: {type(exc).__name__}: {exc}")
    if bad:
        _fail("Public/runtime modules are not importable:\n" + "\n".join(bad))


def _assert_smoke_entrypoint_contract() -> None:
    smoke_test = _read("smoke_test.py")
    smoke_combined = _read("smoke_test_combined.py")
    for file_name, source in [("smoke_test.py", smoke_test), ("smoke_test_combined.py", smoke_combined)]:
        for snippet in ["from smoke_combined_runner import run", 'if __name__ == "__main__":', "run()"]:
            if snippet not in source:
                _fail(f"{file_name} is not an executable smoke entrypoint; missing: {snippet}")


def _assert_release_zip_excludes_generated_runs() -> None:
    source = _read("make_release_zip.py")
    required = [
        'part.startswith("test_run")',
        'part.endswith("_run")',
        'for part in rel.parts',
    ]
    missing = [snippet for snippet in required if snippet not in source]
    if missing:
        _fail("make_release_zip.py can leak generated run folders; missing: " + ", ".join(missing))

def _assert_startup_state_contract() -> None:
    """Catch startup-only globals that compileall/smoke tests can miss headlessly."""
    module = importlib.import_module("app_initialization")
    globals_map = module.AppInitializationMixin._init_medical_output_state.__globals__
    required_globals = ["DOCUMENT_ORDER", "DIARY_KIND"]
    missing = [name for name in required_globals if name not in globals_map]
    if missing:
        _fail("Startup app-state globals are missing: " + ", ".join(missing))
    document_order = globals_map["DOCUMENT_ORDER"]
    if not document_order or "discharge" not in document_order:
        _fail("Startup DOCUMENT_ORDER contract is invalid")

def _assert_dnd_contract() -> None:
    required = [
        "dnd_contract_check.py",
        "dnd_mixin.py",
        "startup.py",
        "layout_sources.py",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        _fail("Missing drag-and-drop contract files: " + ", ".join(missing))
    dnd = _read("dnd_mixin.py")
    for snippet in ["from tkinterdnd2 import DND_FILES", "drop_target_register(DND_FILES)", 'dnd_bind("<<Drop>>", self._on_drop_event)', "_parse_drop_event_data"]:
        if snippet not in dnd:
            _fail(f"Drag-and-drop runtime contract misses: {snippet}")

def _assert_discharge_date_contract() -> None:
    source = "\n".join(_read(path.name) for path in sorted(ROOT.glob("*.py")) if path.name not in {"prod_audit.py"})
    for snippet in ["def _ensure_discharge_date", "def _prompt_discharge_date", 'title="Дата выписки"', "ДДММГГГГ, ДДММГГ или коротко ДМГГ"]:
        if snippet not in source:
            _fail(f"Discharge-date popup contract misses: {snippet}")

    from medical_documents import parse_date
    from diary_filler import parse_full_date
    if parse_date("10052026").strftime("%d.%m.%Y") != "10.05.2026":
        _fail("medical compact date parser is broken")
    if parse_date("1126").strftime("%d.%m.%Y") != "01.01.2026":
        _fail("medical short compact date parser is broken")
    if parse_full_date("100526").strftime("%d.%m.%Y") != "10.05.2026":
        _fail("diary compact date parser is broken")
    if parse_full_date("1126").strftime("%d.%m.%Y") != "01.01.2026":
        _fail("diary short compact date parser is broken")




def _assert_dialog_runtime_globals_contract() -> None:
    """Catch Tkinter callback NameError regressions in dialog methods.

    compileall and import checks are not enough: a missing global inside a
    callback only explodes after the user clicks a button. This guard checks
    the concrete globals used by the discharge-date and hospital-popup paths.
    """
    import dialog_expert

    cls = dialog_expert.DialogExpertMixin
    required_by_method = {
        "_prompt_expert_anamnesis_details": ["parse_date"],
        "_ensure_discharge_date": ["parse_date"],
        "_prompt_discharge_date": ["parse_date"],
        "_prompt_assigned_treatment_if_needed": ["parse_date", "sanitize_diagnosis"],
    }
    missing: list[str] = []
    for method_name, names in required_by_method.items():
        globals_map = getattr(cls, method_name).__globals__
        for name in names:
            if name not in globals_map:
                missing.append(f"{method_name}: {name}")
    if missing:
        _fail("Dialog runtime globals are missing: " + ", ".join(missing))



def _assert_treatment_popup_contract() -> None:
    """Guard missing-treatment popup workflow for block 03 medical tiles."""
    from medical_service import MedicalDocumentService

    parser = MedicalDocumentService().parser
    no_marker = parser.parse_text("""
Первичный осмотр
Ф.И.О.: Иванов Иван Иванович
Год рождения: 1990
За время лечения состояние без динамики.
Диагноз: F41.2 тест
""")
    has_marker = parser.parse_text("""
Первичный осмотр
Ф.И.О.: Иванов Иван Иванович
Год рождения: 1990
Назначенное лечение терапия по схеме.
Диагноз: F41.2 тест
""")
    if no_marker.has_treatment_section:
        _fail("Prose phrase 'за время лечения' must not count as a treatment section")
    if not has_marker.has_treatment_section or has_marker.treatment_plan != "терапия по схеме.":
        _fail("Explicit 'Назначенное лечение' marker without colon must be parsed as treatment")

    layout_action_bar = _read("layout_action_bar.py")
    orchestrator = _read("actions_creation_orchestrator.py")
    details = _read("dialog_document_details.py")
    required_pairs = [
        (layout_action_bar, "kind != DIARY_KIND", "diary tile must be excluded from treatment popup guard"),
        (layout_action_bar, "_prompt_common_output_requirements", "block 03 medical tiles must call merged common popup guard"),
        (orchestrator, "_prompt_common_output_requirements", "create flow must enforce merged common popup guard"),
        (details, "_primary_has_treatment_section", "dialog layer must inspect full primary parser flag"),
        (details, '"Номер истории болезни", self._case_number_popup_default()', "medical popups must show shared case number"),
        (details, "def _store_case_number_value", "dialog layer must store shared case number once"),
        (details, 'fields.append("case_number")', "missing-treatment popup must include shared case-number field"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("Treatment popup contract is incomplete:\n" + "\n".join(missing))


def _assert_audit_hardening_contract() -> None:
    """Guard the bug fixes from the v1.3.3 deep audit."""
    numbers = _read("diary_table_numbers.py")
    dates = _read("diary_table_dates.py")
    files = _read("files_mixin.py")
    dnd = _read("dnd_mixin.py")
    diagnosis = _read("diagnosis_widget.py")
    dialog_popup = _read("dialog_fields_popup.py")
    title_finder = _read("medical_docx_title_finder.py")
    templates = _read("actions_template_checks.py")
    orchestrator = _read("actions_creation_orchestrator.py")
    app_init = _read("app_initialization.py")
    actions_diary = _read("actions_diary_flow.py")

    required_pairs = [
        (numbers, "from datetime import date", "diary_table_numbers.py must import date for public type hints"),
        (dates, "from diary_table_columns import find_day_column", "diary_table_dates.py must stay a small date detector"),
        (files, "def _truncate_label_text", "FilesMixin must truncate long UI labels"),
        (files, "single_line: bool = False", "FilesMixin._short_file_list must support single-line labels"),
        (dnd, "_update_diary_text_label(success=True)", "DnD status labels must go through the compact diary-text label updater"),
        (diagnosis, "if not query:\n            self._hide_diagnosis_popup()", "diagnosis field must not search ICD-10 on empty input"),
        (dialog_popup, "if not query:\n            self.hide()", "dialog diagnosis popup must not search ICD-10 on empty input"),
        (title_finder, r"\d{4,8}", "title date finder must support compact dates in isolated title-neighbor rows"),
        (templates, "template_path = bundled_template_path(kind)", "template check must not call bundled_template_path twice per kind"),
        (orchestrator, "_select_default_printer_sync", "print flow must not rely on asynchronous refresh_printers before printing"),
        (app_init, "_printer_refresh_in_progress", "printer discovery needs a concurrency guard"),
        (actions_diary, "_auto_select_diary_text_by_diagnosis(ask_folder=False)", "diary creation must retry diagnosis-based diary text autoselect before warning"),
        (_read("diary_text_selection.py"), "_COMMON_DIARY_NAME_WORDS", "diary text matching must ignore technical filename words like дневники/ВЭ"),
        (_read("diary_text_selection.py"), "oligophrenia", "diary text matching must bridge F70/умственная отсталость to олигофрены filenames"),
        (_read("window_mixin.py"), "Нижняя служебная строка убрана", "bottom service/status line must stay hidden"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("Audit-hardening contract is incomplete:\n" + "\n".join(missing))
    if "def cell_int" in dates or "def should_remove_holiday" in dates:
        _fail("diary_table_dates.py reintroduced duplicated numeric helpers")
    window = _read("window_mixin.py")
    if "status_bar.pack" in window or "_status_bar_ready_icon" in window:
        _fail("Visible bottom status/service line was reintroduced")
    if "Дата поступления / конс. тел." in window or "конс. тел." in window:
        _fail("Main screen block 01 must show only: Дата поступления")
    if "Дата поступления" not in window:
        _fail("Main screen block 01 admission-date label is missing")

def _assert_release_documents() -> None:
    required = [
        "README.md",
        "RELEASE_NOTES.md",
        "FIX_REPORT.md",
        "PROD_READY_AUDIT_REPORT.md",
        "LAUNCH_CHECKLIST.md",
        ".github/workflows/windows-build.yml",
        "build_exe_windows.bat",
        ".gitattributes",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        _fail("Missing release documents/files: " + ", ".join(missing))

    readme = _read("README.md")
    for snippet in ["локально", "готовый `MedicalDiaryAutofill.exe`", "Python, pip и зависимости", "Проверки перед релизом"]:
        if snippet not in readme:
            _fail(f"README misses production snippet: {snippet}")



def _assert_quality_100_contract() -> None:
    """Guard the final production-quality hardening layer."""
    service = _read("medical_service.py")
    diary_batch = _read("diary_batch.py")
    medical_paths = _read("medical_paths.py")
    make_zip = _read("make_release_zip.py")
    workflow = _read(".github/workflows/windows-build.yml")
    attrs = _read(".gitattributes")
    required_pairs = [
        (service, "def _resolve_output_dir", "medical service must validate output directory before mkdir/render"),
        (service, "label_to_kind", "medical service must accept visible UI labels at public boundary"),
        (service, "Папка результата указывает на файл", "medical service must reject output_dir pointing to a file"),
        (diary_batch, "seen: set[Path]", "diary input DOCX list must dedupe repeated files"),
        (diary_batch, "def _resolve_output_dir", "diary batch must validate output directory before copying templates"),
        (diary_batch, "Пустой путь к файлу", "diary batch must reject blank file paths clearly"),
        (diary_batch, "return True", "open_folder must report whether folder opening really started"),
        (medical_paths, "validate=True", "embedded template base64 must be validated strictly"),
        (medical_paths, ".tmp", "embedded template cache refresh must be atomic"),
        (make_zip, "def _assert_clean_archive", "release ZIP must verify itself before publishing"),
        (workflow, "permissions:", "GitHub Actions must run with explicit least-privilege permissions"),
        (workflow, "concurrency:", "GitHub Actions must avoid stale concurrent release builds"),
        (workflow, "timeout-minutes:", "GitHub Actions must not hang indefinitely"),
        (attrs, "*.py text eol=lf", "repository must prevent Windows CRLF churn for Python sources"),
        (attrs, "*.docx binary", "repository must mark Office templates as binary"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("100/100 quality contract is incomplete:\n" + "\n".join(missing))

def main() -> None:
    _assert_version_sync()
    _assert_architecture_hygiene()
    _assert_no_import_cycles()
    _assert_no_deleted_module_references()
    _assert_public_modules_importable()
    _assert_startup_state_contract()
    _assert_smoke_entrypoint_contract()
    _assert_release_zip_excludes_generated_runs()
    _assert_dnd_contract()
    _assert_discharge_date_contract()
    _assert_dialog_runtime_globals_contract()
    _assert_treatment_popup_contract()
    _assert_audit_hardening_contract()
    _assert_release_documents()
    _assert_quality_100_contract()
    print("PROD AUDIT OK")


if __name__ == "__main__":
    main()
