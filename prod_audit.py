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
TARGET_VERSION = "1.4.0"
TARGET_VERSION_LABEL = "v1.4.0-final-user-flow"
MAX_PYTHON_FILES = 125
MAX_TINY_PYTHON_FILES = 25
# Release/CI probes are executable quality gates, not runtime architecture.
# Keep the 125-file runtime budget intact instead of "fixing" the gate by
# silently raising it whenever a new QA entrypoint is added.
RELEASE_ONLY_ENTRYPOINTS = {"gui_runtime_check.py", "verify_built_exe.py"}

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
    "diary_templates_mixin.py",
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
    "diary_paths.py",
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
    "gui_runtime_check.py",
    "verify_built_exe.py",
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
        "version_info tuple": "filevers=(1, 4, 0, 0)" in version_info and "prodvers=(1, 4, 0, 0)" in version_info,
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

    runtime_py_files = [p for p in py_files if p.name not in RELEASE_ONLY_ENTRYPOINTS]
    if len(runtime_py_files) > MAX_PYTHON_FILES:
        _fail(
            f"Too many runtime Python files after dust collapse: "
            f"{len(runtime_py_files)} > {MAX_PYTHON_FILES}"
        )

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

def _assert_final_user_flow_gate_contract() -> None:
    """Guard the last-mile Windows/UI/release path, not only document internals."""
    main_source = _read("main.py")
    startup = _read("startup.py")
    layout = _read("layout_sources.py")
    files = _read("files_mixin.py")
    workflow = _read(".github/workflows/windows-build.yml")
    release_workflow = _read(".github/workflows/release.yml")
    verify_exe = _read("verify_built_exe.py")
    gui_check = _read("gui_runtime_check.py")

    required_pairs = [
        (main_source, "MEDICAL_AUTOFILL_STARTUP_PROBE", "packaged app needs a non-interactive startup probe"),
        (main_source, "_register_tkinterdnd_drop_targets", "packaged startup probe must prove TkDND registration"),
        (startup, "require_dnd: bool = False", "release probe must be able to fail closed on TkDND"),
        (layout, "primary_document_type_display_widget = type_canvas", "primary document type must be read-only"),
        (files, "Выберите папку «Даты» с шаблонами 01–31", "Dates must use one direct folder dialog"),
        (files, "def _confirm_manual_output_dir_for_patient_switch", "manual output folder needs patient-switch confirmation"),
        (files, "self._confirm_manual_output_dir_for_patient_switch()", "patient switch must invoke output-folder confirmation"),
        (workflow, "python gui_runtime_check.py", "Windows CI must instantiate and drive the real Tk UI"),
        (workflow, "python verify_built_exe.py", "Windows CI must run the exact built EXE"),
        (verify_exe, "_pe_has_authenticode_signature", "packaged EXE verifier must inspect Authenticode presence"),
        (verify_exe, "MEDICAL_AUTOFILL_REQUIRE_SIGNED_EXE", "official release verifier must fail closed when unsigned"),
        (gui_check, "event_generate", "GUI runtime check must exercise real widget events"),
        (release_workflow, "SIGNING_CERT_PFX_BASE64", "official release must require a signing certificate"),
        (release_workflow, "signtool verify", "official release must verify Authenticode"),
        (release_workflow, "gh release create", "official release needs a stable GitHub Release channel"),
    ]
    missing = [message for source, snippet, message in required_pairs if snippet not in source]
    if missing:
        _fail("Final user-flow gate is incomplete:\n" + "\n".join(missing))
    choose_start = files.index("    def choose_diary_files")
    choose_end = files.index("    def _short_file_list", choose_start)
    choose_source = files[choose_start:choose_end]
    if "askopenfilename" in choose_source or "askopenfilenames" in choose_source:
        _fail("Dates UI reintroduced the old two-dialog file/folder flow")


def _assert_discharge_date_contract() -> None:
    source = "\n".join(_read(path.name) for path in sorted(ROOT.glob("*.py")) if path.name not in {"prod_audit.py"})
    for snippet in ["def _ensure_discharge_date", "def _prompt_discharge_date", 'title="Дата выписки"', "ДДММГГГГ, ДДММГГ или коротко ДМГГ"]:
        if snippet not in source:
            _fail(f"Discharge-date popup contract misses: {snippet}")

    medical_date_source = _read("medical_formatting.py")
    diary_date_source = _read("diary_dates.py")
    shared_date_source = _read("shared_dates.py")
    for module_name, module_source in (
        ("medical_formatting.py", medical_date_source),
        ("diary_dates.py", diary_date_source),
    ):
        if "from shared_dates import parse_date_value" not in module_source:
            _fail(f"{module_name} bypasses the canonical shared date parser")
        for duplicate in ("def _parse_compact_date_digits", "def _candidate_date", "def _two_digit_year_to_full"):
            if duplicate in module_source:
                _fail(f"{module_name} duplicates canonical date logic: {duplicate}")
    for required_shared_symbol in (
        "def parse_date_value",
        "def _parse_compact_date_digits",
        "MIN_CLINICAL_YEAR = 1900",
        "MAX_CLINICAL_YEAR = 2200",
    ):
        if required_shared_symbol not in shared_date_source:
            _fail(f"shared date parser contract misses: {required_shared_symbol}")

    from shared_dates import parse_date_value
    from medical_documents import parse_date
    from diary_filler import parse_full_date
    for raw, expected in {
        "090926": "09.09.2026",
        "09092026": "09.09.2026",
        "1126": "01.01.2026",
        "10526": "01.05.2026",
        "3112026": "31.01.2026",
    }.items():
        parsed_shared = parse_date_value(raw)
        if parsed_shared is None or parsed_shared.strftime("%d.%m.%Y") != expected:
            _fail(f"canonical shared date parser is broken for {raw}")

    if parse_date("10052026").strftime("%d.%m.%Y") != "10.05.2026":
        _fail("medical compact date parser is broken")
    if parse_date("090926").strftime("%d.%m.%Y") != "09.09.2026":
        _fail("medical DDMMYY compact date parser is broken")
    if parse_date("1126").strftime("%d.%m.%Y") != "01.01.2026":
        _fail("medical short compact date parser is broken")
    if parse_full_date("100526").strftime("%d.%m.%Y") != "10.05.2026":
        _fail("diary compact date parser is broken")
    if parse_full_date("1126").strftime("%d.%m.%Y") != "01.01.2026":
        _fail("diary short compact date parser is broken")

    from dialog_dates import DialogDatesMixin
    live_cases = {
        "09092": "09092",
        "090926": "09.09.26",
        "090920": "090920",  # may still become 09092026
        "0909202": "0909202",
        "09092026": "09.09.2026",
        "101202": "101202",  # prefix of legacy 1012026 -> 01.01.2026
        "1012026": "01.01.2026",
        "1126": "1126",
        "09.09.2026": "09.09.2026",
    }
    for raw, expected in live_cases.items():
        actual = DialogDatesMixin._format_date_input_live(raw)
        if actual != expected:
            _fail(f"live popup date mask is broken for {raw}: {actual!r} != {expected!r}")

    for compact, expected in {
        "090926": "09.09.2026",
        "09092026": "09.09.2026",
        "1012026": "01.01.2026",
        "1092026": "01.09.2026",
    }.items():
        visible = ""
        for char in compact:
            visible += char
            visible = DialogDatesMixin._format_date_input_live(visible)
        parsed = parse_date(visible)
        if not parsed or parsed.strftime("%d.%m.%Y") != expected:
            _fail(f"live popup date mask corrupts typed {compact}: visible={visible!r}")
    if '<KeyRelease>' not in _read("dialog_dates.py"):
        _fail("popup date fields do not apply the live date mask while typing")





def _assert_shared_gender_contract() -> None:
    """Keep patient-gender logic domain-neutral and single-sourced."""
    shared = _read("shared_gender.py")
    medical = _read("medical_gender.py")
    diary_facade = _read("diary_gender.py")
    diary_constants = _read("diary_constants.py")
    diary_batch = _read("diary_batch.py")
    diary_writer_apply = _read("diary_writer_apply.py")

    for required in (
        "GENDER_WORD_PAIRS: tuple[tuple[str, str], ...]",
        "def detect_gender_from_patient_name",
        "def adapt_text_to_patient_gender",
        "def convert_text_gender",
    ):
        if required not in shared:
            _fail(f"shared gender contract misses: {required}")

    if "from diary_filler" in medical or "from diary_constants" in medical:
        _fail("medical gender layer depends on the diary domain")
    if "from shared_gender import" not in medical:
        _fail("medical gender layer bypasses the canonical shared gender core")

    if "GENDER_WORD_PAIRS: tuple" in diary_constants:
        _fail("diary_constants.py duplicates the canonical gender word pairs")
    if "from shared_gender import GENDER_WORD_PAIRS" not in diary_constants:
        _fail("diary_constants.py must only re-export canonical gender word pairs")
    if "from shared_gender import" not in diary_facade:
        _fail("diary_gender.py is not a compatibility facade over shared_gender")
    for duplicate in ("def detect_gender_from_patient_name", "def adapt_text_to_patient_gender"):
        if duplicate in diary_facade:
            _fail(f"diary_gender.py duplicates canonical gender logic: {duplicate}")
    for name, source in (("diary_batch.py", diary_batch), ("diary_writer_apply.py", diary_writer_apply)):
        if "from shared_gender import" not in source:
            _fail(f"{name} bypasses the canonical shared gender core")

    from shared_gender import GENDER_WORD_PAIRS, adapt_text_to_patient_gender, detect_gender_from_patient_name
    from diary_gender import adapt_text_to_patient_gender as legacy_adapt
    from diary_gender import detect_gender_from_patient_name as legacy_detect

    if len(GENDER_WORD_PAIRS) < 190:
        _fail("canonical gender vocabulary unexpectedly lost known clinical pairs")
    for fio, expected in (
        ("Иванов И.И.", "male"),
        ("Иванова И.И.", "female"),
        ("Шевченко Алексей Сергеевич", "male"),
        ("Шевченко Анна Сергеевна", "female"),
        ("Шевченко А.А.", None),
    ):
        if detect_gender_from_patient_name(fio) != expected:
            _fail(f"canonical gender detection is broken for {fio}")
        if legacy_detect(fio) != expected:
            _fail(f"legacy gender facade diverges for {fio}")
    sample = "Пациент пришёл самостоятельно, был вялым и несобранным."
    if adapt_text_to_patient_gender(sample, "female") != legacy_adapt(sample, "female"):
        _fail("legacy gender facade diverges from canonical shared gender adaptation")



def _assert_shared_paths_contract() -> None:
    """Keep filename sanitation and collision handling on one shared core."""
    shared = _read("shared_paths.py")
    medical = _read("medical_formatting.py")
    diary_batch = _read("diary_batch.py")
    diary_facade = _read("diary_filler.py")

    for required in (
        "def sanitize_filename",
        "def resolve_available_path",
        "def safe_filename_part",
        "def make_diary_output_name",
    ):
        if required not in shared:
            _fail(f"shared path contract misses: {required}")
    if "from shared_paths import resolve_available_path, sanitize_filename" not in medical:
        _fail("medical filename/path policy bypasses shared_paths")
    for duplicate in ("for counter in range(2, 10000)", "for idx in range(2, 10000)"):
        if duplicate in medical:
            _fail("medical_formatting.py duplicates shared collision logic")
    if "from shared_paths import" not in diary_batch:
        _fail("diary batch bypasses shared_paths")
    if "from shared_paths import *" not in diary_facade:
        _fail("diary public facade must re-export shared path helpers")
    if (ROOT / "diary_paths.py").exists():
        _fail("legacy diary_paths.py reintroduced a second path architecture")

    from medical_formatting import available_path as medical_available_path, safe_filename
    from shared_paths import available_path as diary_available_path, safe_filename_part
    import tempfile

    if safe_filename("CON.txt") != "CON.txt_":
        _fail("medical reserved-name sanitation changed")
    try:
        safe_filename_part("")
    except ValueError as exc:
        if str(exc) != "Введите ФИО пациента":
            _fail("diary empty-name policy changed")
    else:
        _fail("diary empty-name policy must reject blank FIO")
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        medical_base = root / "medical.docx"
        diary_base = root / "diary.docx"
        medical_base.write_text("x", encoding="utf-8")
        diary_base.write_text("x", encoding="utf-8")
        if medical_available_path(medical_base).name != "medical (2).docx":
            _fail("medical collision suffix changed")
        if diary_available_path(diary_base).name != "diary_2.docx":
            _fail("diary collision suffix changed")


def _assert_patient_session_reset_contract() -> None:
    """Keep all patient-scoped reset decisions in one canonical registry."""
    source = _read("files_mixin.py")
    tree = ast.parse(source, filename="files_mixin.py")

    def literal(name: str):
        for node in tree.body:
            if isinstance(node, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                    return ast.literal_eval(node.value)
        _fail(f"patient-session reset registry is missing: {name}")

    always_vars = dict(literal("PATIENT_SESSION_ALWAYS_VAR_DEFAULTS"))
    tracked_vars = dict(literal("PATIENT_SESSION_TRACKED_UI_VAR_DEFAULTS"))
    switch_vars = dict(literal("PATIENT_SESSION_SWITCH_ONLY_VAR_DEFAULTS"))
    switch_attrs = dict(literal("PATIENT_SESSION_SWITCH_ONLY_ATTR_DEFAULTS"))
    switch_lists = set(literal("PATIENT_SESSION_SWITCH_ONLY_LIST_ATTRS"))

    required_always = {
        "assigned_treatment_var", "case_number_var",
        "expert_work_status_var", "expert_work_org_var", "expert_position_var",
        "expert_sick_leave_needed_var", "expert_sick_leave_from_var", "expert_sick_leave_number_var",
        "vk_mse_work_org_var", "vk_mse_position_var",
        "sick_leave_vk_work_org_var", "sick_leave_vk_position_var", "sick_leave_vk_work_position_var",
    }
    required_tracked = {"patient_name_var", "admission_date_var", "discharge_date_var", "diagnosis_var"}
    required_switch = {
        "rvk_act_number_var", "rvk_military_commissariat_var", "rvk_work_position_var",
        "vk_date_var", "vk_protocol_number_var", "vk_protocol_date_var",
        "sick_leave_vk_date_var", "sick_leave_vk_protocol_number_var",
        "sick_leave_vk_protocol_date_var", "sick_leave_vk_commission_date_var",
        "commission_date_var", "commission_number_var", "epi_path_var",
    }
    for label, required, actual in (
        ("always", required_always, set(always_vars)),
        ("tracked", required_tracked, set(tracked_vars)),
        ("switch", required_switch, set(switch_vars)),
    ):
        missing = sorted(required - actual)
        if missing:
            _fail(f"patient-session {label} registry misses: " + ", ".join(missing))
    if {"status_files", "diary_files"} - switch_lists:
        _fail("patient-session switch registry must own selected diary inputs")
    if {"_diary_text_files_auto_selected", "_diary_files_auto_selected"} - set(switch_attrs):
        _fail("patient-session switch registry must own diary auto-selection flags")

    if "def _apply_patient_session_defaults" not in source:
        _fail("canonical patient-session reset boundary is missing")
    if "self._apply_patient_session_defaults(clear_patient_inputs=clear_patient_inputs)" not in source:
        _fail("primary-document reset bypasses the canonical patient-session boundary")
    if "self.data = PatientData()" not in source or "PATIENT_SESSION_TRACKED_UI_VAR_DEFAULTS" not in source:
        _fail("patient model or tracked UI fields are outside the canonical reset boundary")

    reset_section = source.split("def _reset_primary_document_runtime_state", 1)[1].split("def _primary_type_from_parsed_data", 1)[0]
    for name in required_always | required_tracked | required_switch:
        if f"self.{name}.set(" in reset_section:
            _fail(f"patient field reset escaped the canonical registry: {name}")


def _assert_diary_service_boundary() -> None:
    """Keep the production GUI on the paragraph diary architecture only."""
    actions = _read("actions_diary_flow.py")
    service = _read("diary_service.py")
    batch = _read("diary_batch.py")
    app_init = _read("app_initialization.py")

    dead_legacy_state = (
        "reset_each_file_var",
        "keep_signature_var",
        "fill_months_var",
        "remove_holiday_rows_var",
    )
    leaked = [name for name in dead_legacy_state if name in app_init]
    if leaked:
        _fail("dead legacy diary UI state was reintroduced: " + ", ".join(leaked))

    if "from diary_service import DiaryService" not in actions or "DiaryService().create_text_diaries" not in actions:
        _fail("GUI diary flow bypasses the production DiaryService")
    for forbidden in ("fill_diary_batch", "text_output"):
        if forbidden in actions:
            _fail(f"GUI diary flow still selects legacy architecture through: {forbidden}")
    if "class DiaryService" not in service or "def create_text_diaries" not in service:
        _fail("Production DiaryService contract is missing")
    if "text_output" in service or "from diary_batch import fill_diary_batch" in service:
        _fail("Production DiaryService is coupled back to the legacy boolean/table facade")
    if "def create_text_diaries" not in batch:
        _fail("Canonical paragraph diary entry point is missing from diary_batch.py")

    # Importing the production DiaryService must not eagerly load the legacy
    # table writer. Keep only the narrow date-source helpers at module scope;
    # the old writer remains available through the lazy compatibility proxy.
    batch_tree = ast.parse(batch, filename="diary_batch.py")
    top_level_from = {
        node.module
        for node in batch_tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = sorted({"diary_writer", "diary_table"} & top_level_from)
    if forbidden:
        _fail("production diary batch eagerly imports legacy modules: " + ", ".join(forbidden))
    if "from diary_table_columns import" not in batch or "from diary_table_numbers import" not in batch:
        _fail("production date-source reader lost its narrow table helper imports")
    if "def fill_diary_file(*args, **kwargs)" not in batch or "legacy_fill_diary_file" not in batch:
        _fail("legacy fill_diary_file compatibility proxy is missing")

def _assert_joint_diary_semantics_contract() -> None:
    """Joint/head signatures are clinical entry semantics, not template formatting."""
    batch = _read("diary_batch.py")
    constants = _read("diary_constants.py")
    actions = _read("actions_diary_flow.py")

    required_constants = (
        'DIARY_JOINT_HEAD_EXAM_TITLE = "Совместный осмотр с зав. отделением"',
        'DIARY_TREATING_DOCTOR_SIGNATURE = "Лечащий врач Балаганин С.В."',
        'DIARY_DEPARTMENT_HEAD_SIGNATURE = "Зав.отделением Можарова Е.А."',
    )
    for required in required_constants:
        if required not in constants:
            _fail(f"canonical diary joint-exam contract misses: {required}")
    for required in (
        "class TextDiaryEntry",
        "is_joint_head_exam: bool",
        "is_joint_head_exam=(index % 3 == 0)",
        "if entry.is_joint_head_exam:",
        "doctor_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT",
        "head_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT",
    ):
        if required not in batch:
            _fail(f"semantic joint-diary implementation misses: {required}")
    if "_signature_lines_from_diary_sources" in batch:
        _fail("source-template signatures may not decide production joint-exam semantics")
    if "doctor_name=" in actions or "head_name=" in actions:
        _fail("patient/input signature fields leaked back into canonical diary signing roles")

    from datetime import date
    import diary_batch as diary_batch_module
    entries, final_rows, _ = diary_batch_module._build_text_diary_entries(
        ["Пациент спокоен"],
        [date(2026, 1, day) for day in (2, 3, 4, 5, 6, 7)],
        discharge_date_value=date(2026, 1, 7),
        force_final_diary=True,
        repeat_statuses=True,
        patient_gender="male",
    )
    if [entry.sequence_number for entry in entries if entry.is_joint_head_exam] != [3, 6]:
        _fail("every-third-diary joint examination semantics changed")
    if final_rows != 1 or not entries[-1].is_final:
        _fail("joint-exam semantics broke the independent final-discharge diary")


def _assert_admission_occurrence_contract() -> None:
    """Первично/повторно is one explicit patient fact shared by discharge and RVK."""
    model = _read("medical_models.py")
    service = _read("medical_service.py")
    flow = _read("actions_medical_flow.py")
    orchestrator = _read("actions_creation_orchestrator.py")
    details = _read("dialog_document_details.py")
    expert = _read("dialog_expert.py")
    reset = _read("files_mixin.py")
    discharge_renderer = _read("medical_renderer_primary.py")
    rvk_renderer = _read("medical_renderer_special.py")
    parser = _read("medical_parser_core.py")

    required_pairs = (
        (model, 'ADMISSION_OCCURRENCE_OPTIONS = ("первично", "повторно")', "canonical occurrence options missing"),
        (model, "admission_occurrence: str", "PatientData lost admission occurrence"),
        (model, "def strip_admission_occurrence_prefix", "clinical admission tail is not separated from occurrence"),
        (flow, "data.admission_occurrence = normalize_admission_occurrence", "generation snapshot does not capture occurrence"),
        (service, 'if {"discharge", "rvk"} & selected_set:', "service does not own occurrence validation boundary"),
        (service, "первично или повторно", "service does not reject missing occurrence"),
        (reset, '("admission_occurrence_var", "")', "occurrence leaks between patients"),
        (orchestrator, "or not self._current_admission_occurrence()", "RVK flow can bypass occurrence popup"),
        (expert, 'detail_fields.append("admission_occurrence")', "discharge popup does not ask occurrence"),
        (details, '("первично", "повторно")', "RVK popup lost binary occurrence choices"),
        (discharge_renderer, "data.admission_occurrence", "discharge renderer ignores occurrence"),
        (rvk_renderer, "data.admission_occurrence", "RVK renderer ignores occurrence"),
        (parser, "strip_admission_occurrence_prefix(data.admission)", "parser can duplicate legacy occurrence word"),
    )
    for source, snippet, message in required_pairs:
        if snippet not in source:
            _fail(message)

    from medical_models import normalize_admission_occurrence, strip_admission_occurrence_prefix
    if normalize_admission_occurrence("ПОВТОРНО") != "повторно":
        _fail("occurrence normalization changed")
    if normalize_admission_occurrence("иногда"):
        _fail("invalid occurrence must never be accepted")
    if strip_admission_occurrence_prefix("повторно добровольно") != "добровольно":
        _fail("legacy occurrence prefix is not separated from admission clinical text")


def _assert_diagnosis_diary_text_contract() -> None:
    """Ordinary diaries come from diagnosis template; discharge text is universal."""
    batch = _read("diary_batch.py")
    constants = _read("diary_constants.py")
    selection = _read("diary_text_selection.py")

    batch_tree = ast.parse(batch, filename="diary_batch.py")
    imported_from_constants = {
        alias.name
        for node in batch_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "diary_constants"
        for alias in node.names
    }
    if "FINAL_DIARY_TEXT" not in imported_from_constants:
        _fail("production diary route lost the universal final-discharge diary text")
    if "adapt_text_to_patient_gender(FINAL_DIARY_TEXT" not in batch:
        _fail("final discharge diary is no longer generated from FINAL_DIARY_TEXT")
    if "Состояние улучшилось." not in constants or "На текущую дату оформлена выписка" not in constants:
        _fail("canonical universal final diary text was changed or removed")

    for required in (
        "def _direct_diagnosis_name_rank",
        "def _safe_legacy_diagnosis_fallback",
        "if direct_rank == 0 and not _safe_legacy_diagnosis_fallback",
    ):
        if required not in selection:
            _fail(f"diagnosis-owned diary selection guard is missing: {required}")

    from diary_text_selection import (
        _direct_diagnosis_name_rank,
        _safe_legacy_diagnosis_fallback,
        diary_diagnosis_match_score,
    )

    if _direct_diagnosis_name_rank("F20 Шизофрения", "Шизофрения") != 2:
        _fail("exact diagnosis filename relation no longer has top priority")
    unsafe_cases = (
        ("F32.0 Легкий депрессивный эпизод", "Тяжелая депрессия"),
        ("F06.6 Органическое эмоционально лабильное расстройство", "Органическая депрессия"),
        ("F20.2 Кататоническая шизофрения", "Параноидная шизофрения"),
    )
    for diagnosis, filename in unsafe_cases:
        score = diary_diagnosis_match_score(diagnosis, filename)
        if _safe_legacy_diagnosis_fallback(diagnosis, filename, score):
            _fail(f"related but wrong diagnosis may be auto-selected: {diagnosis} -> {filename}")

    legacy_cases = (
        ("F70.0 Легкая умственная отсталость", "дневники ВЭ олигофрены"),
        ("F32.0 Легкий депрессивный эпизод", "дневники ВЭ легкая депрессия с датами"),
        ("F06.6 Органическое эмоционально лабильное расстройство", "дневники ВЭ легкая органика"),
    )
    for diagnosis, filename in legacy_cases:
        score = diary_diagnosis_match_score(diagnosis, filename)
        if not _safe_legacy_diagnosis_fallback(diagnosis, filename, score):
            _fail(f"known physician legacy diagnosis filename stopped matching: {diagnosis} -> {filename}")


def _assert_generation_patient_snapshot_contract() -> None:
    """One create action must use one canonical PatientData snapshot."""
    orchestrator = _read("actions_creation_orchestrator.py")
    medical = _read("actions_medical_flow.py")
    diary = _read("actions_diary_flow.py")

    if "generation_patient_data = self._capture_generation_patient_data" not in orchestrator:
        _fail("generation orchestrator does not capture canonical patient data once")
    if orchestrator.count("patient_data_snapshot=generation_patient_data") != 2:
        _fail("medical and diary routes must receive the same generation patient snapshot")
    if "def _capture_generation_patient_data" not in medical:
        _fail("canonical generation patient snapshot boundary is missing")
    if "patient_data_snapshot: PatientData | None = None" not in medical:
        _fail("medical generation lost snapshot-compatible boundary")
    if "patient_data_snapshot: PatientData | None = None" not in diary:
        _fail("diary generation lost snapshot-compatible boundary")
    if "data = copy.deepcopy(patient_data_snapshot)" not in medical:
        _fail("medical route may mutate the shared patient snapshot")
    if "patient_data_snapshot.output_fio" not in diary or "patient_data_snapshot.discharge_date" not in diary:
        _fail("diary route does not consume canonical patient identity/dates from the snapshot")
    if "diagnosis_override=(" not in diary or "patient_data_snapshot.diagnosis" not in diary:
        _fail("diary text autoselect is not driven by the canonical patient snapshot")
    if "admission_value_override=(" not in diary or "patient_data_snapshot.admission_date" not in diary:
        _fail("diary date-template autoselect is not driven by the canonical patient snapshot")


def _assert_atomic_generation_contract() -> None:
    """Keep selected medical + diary output on one staged commit boundary."""
    orchestrator = _read("actions_creation_orchestrator.py")
    medical = _read("actions_medical_flow.py")
    diary = _read("actions_diary_flow.py")

    required_orchestrator = (
        "TemporaryDirectory",
        "def _commit_staged_generation",
        "output_dir_override=staging_dir",
        "staged_medical",
        "staged_diary_result",
        "os.replace(staged_path, target)",
        "path.unlink()",
    )
    missing = [item for item in required_orchestrator if item not in orchestrator]
    if missing:
        _fail("atomic generation contract is incomplete: " + ", ".join(missing))
    if "output_dir_override: Path | None = None" not in medical:
        _fail("medical flow cannot render into the shared staging directory")
    if "output_dir_override: Path | None = None" not in diary:
        _fail("diary flow cannot render into the shared staging directory")
    if "output_dir_override if output_dir_override is not None else self._result_output_dir()" not in medical:
        _fail("medical output override is not wired to generation")
    if "output_dir_override if output_dir_override is not None else self._result_output_dir()" not in diary:
        _fail("diary output override is not wired to generation")


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
        (actions_diary, "_auto_select_diary_text_by_diagnosis(", "diary creation must retry diagnosis-based diary text autoselect before warning"),
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
        ".github/workflows/release.yml",
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
    _assert_final_user_flow_gate_contract()
    _assert_discharge_date_contract()
    _assert_patient_session_reset_contract()
    _assert_diary_service_boundary()
    _assert_joint_diary_semantics_contract()
    _assert_admission_occurrence_contract()
    _assert_diagnosis_diary_text_contract()
    _assert_shared_gender_contract()
    _assert_shared_paths_contract()
    _assert_generation_patient_snapshot_contract()
    _assert_atomic_generation_contract()
    _assert_dialog_runtime_globals_contract()
    _assert_treatment_popup_contract()
    _assert_audit_hardening_contract()
    _assert_release_documents()
    _assert_quality_100_contract()
    print("PROD AUDIT OK")


if __name__ == "__main__":
    main()
