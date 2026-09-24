"""Static fail-closed checks for the outer production-safety/support layer."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_RUNTIME_PYTHON_FILES = 126
RELEASE_ONLY_ENTRYPOINTS = {"gui_runtime_check.py", "verify_built_exe.py"}


def fail(message: str) -> None:
    raise SystemExit("PRODUCTION SAFETY GATE FAILED: " + message)


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        fail(f"missing required file: {path}")
    return target.read_text(encoding="utf-8", errors="replace")


def assert_runtime_budget() -> None:
    root_python = sorted(ROOT.glob("*.py"))
    runtime = [path for path in root_python if path.name not in RELEASE_ONLY_ENTRYPOINTS]
    if len(runtime) > MAX_RUNTIME_PYTHON_FILES:
        fail(f"runtime Python budget increased: {len(runtime)} > {MAX_RUNTIME_PYTHON_FILES}")


def assert_behavior_contracts() -> None:
    behavior = read("USER_BEHAVIOR_CONTRACT.md")
    regression = read("REGRESSION_CONTOUR.md")
    if "must **not replace, fork or silently alter the document-creation mechanics**" not in behavior:
        fail("behavior contract lost the no-second-mechanics rule")
    if "_apply_primary_document_path(...)" not in behavior:
        fail("behavior contract lost the canonical desktop-intake handoff")
    if "document_mechanics_guard.py" not in regression:
        fail("regression contour no longer requires the mechanics guard")


def assert_intake_boundary() -> None:
    startup = read("startup.py")
    required = (
        "nothing below generates or edits medical documents",
        "applied = app._apply_primary_document_path(",
        "if applied is False:",
        "The medical/diary generation engine stays",
        "def desktop_intake_scan_wake_candidates",
        "def _desktop_candidate_snapshot",
        "hidden watcher is an outer lifecycle component, not a medical parser",
    )
    missing = [marker for marker in required if marker not in startup]
    if missing:
        fail("desktop intake boundary drifted: " + ", ".join(missing))

    agent_start = startup.find("def run_desktop_intake_agent")
    agent_end = startup.find("# Existing-GUI handoff", agent_start)
    if agent_start < 0 or agent_end < 0:
        fail("desktop intake agent boundary cannot be located")
    agent_body = startup[agent_start:agent_end]
    if "_desktop_candidate_snapshot(root)" not in agent_body:
        fail("closed-GUI watcher no longer uses filesystem-event snapshots")
    if "desktop_intake_scan_primary_candidates(root)" in agent_body:
        fail("closed-GUI watcher regressed to medical pre-classification")
    if "recently_launched" in agent_body:
        fail("closed-GUI watcher regressed to time-based relaunch of unchanged files")

    poll_start = startup.find("def _desktop_poll_intake")
    poll_end = startup.find("def start_desktop_intake_runtime", poll_start)
    if poll_start < 0 or poll_end < 0:
        fail("desktop intake GUI polling boundary cannot be located")
    poll_body = startup[poll_start:poll_end]
    if "_desktop_candidate_snapshot(intake_root)" not in poll_body:
        fail("open GUI no longer uses cheap intake snapshots")
    if "desktop_intake_scan_primary_candidates" in poll_body:
        fail("open GUI regressed to repeated medical parsing on every polling tick")


def assert_self_check_is_outer_only() -> None:
    source = read("main.py")
    if 'SELF_CHECK_ARGUMENT = "--self-check"' not in source:
        fail("packaged technical self-check is missing")
    tree = ast.parse(source, filename="main.py")
    self_check_functions = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_self_check")
    }
    if not self_check_functions:
        fail("self-check functions are missing")
    body = "\n".join(self_check_functions.values())
    forbidden = (
        "MedicalDocumentService",
        "extract_docx_text",
        "parse_primary_document",
        "create_selected_outputs",
        "_create_medical_documents_impl",
        "_create_diaries_impl",
    )
    leaked = [name for name in forbidden if name in body]
    if leaked:
        fail("technical self-check entered document mechanics: " + ", ".join(leaked))


def assert_installer_contract() -> None:
    installer = read("installer/MedicalDiaryAutofill.iss")
    installer_build = read("BUILD_WINDOWS_INSTALLER.bat")
    installer_smoke = read("tools/windows_installer_smoke.ps1")
    intake_e2e = read("tools/windows_desktop_intake_e2e.ps1")
    main_source = read("main.py")

    required = (
        "PrivilegesRequired=lowest",
        "DefaultDirName={localappdata}\\MedicalDiaryAutofill",
        "onboarding-required.flag",
        "CurStepChanged",
        "SaveStringToFile",
        "[Dirs]",
        'Name: "{userdesktop}\\Выписанные пациенты"; Flags: uninsneveruninstall',
        "[Registry]",
        'ValueName: "MedicalDiaryAutofill Intake"',
        'Parameters: "--intake-agent"; Flags: runhidden nowait',
        "[InstallDelete]",
        "desktop-intake-agent-handoff.json",
        "[UninstallDelete]",
        "InitializeUninstall",
        "RegDeleteValue(",
        "taskkill.exe",
        "Result := True;",
    )
    missing = [marker for marker in required if marker not in installer]
    if missing:
        fail("installer contract is incomplete: " + ", ".join(missing))
    if "--uninstall-intake-agent" in installer:
        fail("installer uninstall regressed to a helper command that can block removal")
    if "desktop-intake-agent.heartbeat" not in installer:
        fail("installer no longer manages the watcher heartbeat")
    if "MedicalDiaryAutofill Intake.vbs" not in installer:
        fail("installer no longer removes watcher Startup persistence")
    if "MedicalDiaryAutofill Intake" not in installer:
        fail("installer no longer owns watcher HKCU Run persistence")
    fast_runtime = "dist\\installed\\MedicalDiaryAutofill\\MedicalDiaryAutofill.exe"
    if fast_runtime not in installer_build or "ISCC" not in installer_build:
        fail("installer build script is not bound to the fast onedir runtime")
    if '..\\dist\\installed\\MedicalDiaryAutofill\\*' not in installer:
        fail("installer no longer packages the fast onedir runtime")
    if 'Description: "Запустить MedicalDiaryAutofill"' in installer:
        fail("installer regressed to unsolicited visible post-install launch")
    for marker in (
        "WINDOWS INSTALLER FAST ONEDIR WATCHER BOOTSTRAP AND UNINSTALL SMOKE OK",
        "unins*.exe",
        "--intake-agent",
        "Installer did not create onboarding-required.flag",
        "Installer did not create Desktop\\Выписанные пациенты before first GUI launch",
        "Installer HKCU Run watcher entry does not contain --intake-agent",
        "Installer did not bootstrap a live intake-agent heartbeat",
        "Installer-started intake-agent process is not running before uninstall",
        "Uninstaller removed Desktop\\Выписанные пациенты",
        "Uninstaller removed a user-owned file from Desktop\\Выписанные пациенты",
        "MedicalDiaryAutofill process survived uninstall",
        "HKCU Run watcher entry survived uninstall",
        "Startup watcher script survived uninstall",
    ):
        if marker not in installer_smoke:
            fail(f"installer smoke lost installed-lifecycle marker: {marker}")
    for marker in (
        "WINDOWS DESKTOP INTAKE AUTOLAUNCH E2E OK",
        "--intake-agent",
        "--intake-primary",
        "primary DOCX moved into patient subfolder",
        "IntakeVisibleWindowProbe",
        "Test-AppHasVisibleWindow",
        "visible GUI window",
    ):
        if marker not in intake_e2e:
            fail(f"desktop intake packaged-EXE E2E lost marker: {marker}")
    if "def _activate_root_for_intake" not in main_source:
        fail("desktop intake no longer has explicit pre-popup GUI activation")
    startup_source = read("startup.py")
    for marker in ("PYINSTALLER_RESET_ENVIRONMENT", "def _desktop_visible_popen", "_desktop_visible_popen("):
        if marker not in startup_source:
            fail(f"desktop intake lost independent visible child-process marker: {marker}")
    if "_disable_desktop_intake_persistence" in main_source:
        fail("first-run onboarding can still disable installed intake persistence")
    if 'getattr(app, "_desktop_intake_enabled_for_session", True) is False' in startup_source:
        fail("stale desktop intake preference can still suppress watcher self-heal")
    for marker in (
        "app._desktop_intake_enabled_for_session = True",
        "app._set_desktop_intake_preference(True)",
    ):
        if marker not in main_source:
            fail(f"first-run onboarding lost mandatory intake self-heal marker: {marker}")
    intake_arg_pos = main_source.find("intake_primary = _intake_primary_argument")
    activation_pos = main_source.find("_activate_root_for_intake(root)", intake_arg_pos)
    runtime_pos = main_source.find("start_desktop_intake_runtime(", intake_arg_pos)
    if intake_arg_pos < 0 or activation_pos < 0 or runtime_pos < 0 or activation_pos > runtime_pos:
        fail("desktop intake must activate the GUI before intake runtime schedules primary parsing/popups")
    if "filesandordirs" in installer.casefold():
        fail("installer uses broad recursive uninstall deletion")


def assert_runtime_responsiveness_contract() -> None:
    startup_source = read("startup.py")
    dates = read("dialog_dates.py")
    diagnosis = read("diagnosis_widget.py")
    ui_state = read("actions_ui_state.py")
    blocks = read("medical_docx_blocks.py")
    build = read("build_exe_windows.bat")
    installer = read("installer/MedicalDiaryAutofill.iss")
    main_source = read("main.py")

    if "for suffix in range(10 ** extra_len)" in dates:
        fail("date KeyRelease path regressed to 110-candidate brute-force parser probing")
    for marker in ('for suffix in range(10)', 'self.root.after(120, refresh_after_typing)'):
        source = dates if "range(10)" in marker else diagnosis
        if marker not in source:
            fail(f"responsive UI contract missing marker: {marker}")
    mark_start = ui_state.find("def _mark_manual_field")
    mark_end = ui_state.find("def _set_ui_var", mark_start)
    if mark_start < 0 or mark_end < 0:
        fail("manual-field tracking boundary cannot be located")
    if "_commit_visible_diagnosis_change" in ui_state[mark_start:mark_end]:
        fail("diagnosis StringVar trace performs heavy synchronous work again")

    for marker in (
        "def _active_word_hwnd",
        "def _legacy_doc_cache_path",
        "safe_to_quit =",
        "automation_word_hwnd != user_word_hwnd",
    ):
        if marker not in blocks:
            fail(f"Word ownership/cache contract missing marker: {marker}")

    if "--onedir" not in build or "--distpath dist\\installed" not in build:
        fail("installed Windows runtime is no longer built as fast PyInstaller onedir")
    if '..\\dist\\installed\\MedicalDiaryAutofill\\*' not in installer:
        fail("installer lost fast onedir payload")
    if 'Description: "Запустить MedicalDiaryAutofill"' in installer:
        fail("installer may visibly auto-launch without an explicit user action")

    tree = ast.parse(main_source, filename="main.py")
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "app":
            fail("main.py eagerly imports the full GUI/document graph before watcher dispatch")


def assert_privacy_and_replay_contract() -> None:
    main_source = read("main.py")
    privacy = read("tools/privacy_diagnostics_check.py")
    replay = read("tools/full_patient_replay_check.py")
    golden = read("tools/golden_docx_regression.py")
    gender_matrix = read("tools/gender_generation_regression_matrix.py")
    manifest = read("tests/golden_docx_manifest.json")

    required_main = (
        "def _support_error_code",
        "def _support_sanitize_diagnostics",
        "def _support_write_startup_failure",
        "<REDACTED_PRIMARY>",
        "Код ошибки: {code}",
    )
    missing = [marker for marker in required_main if marker not in main_source]
    if missing:
        fail("privacy-safe startup diagnostics are incomplete: " + ", ".join(missing))
    if "PRIVACY DIAGNOSTICS OK" not in privacy:
        fail("privacy diagnostics executable contract is missing")
    for marker in ("smoke_test.py", "verify_golden", "FULL PATIENT REPLAY OK"):
        if marker not in replay:
            fail(f"full patient replay lost canonical marker: {marker}")
    for marker in ("GOLDEN_RELATIVE_PATHS", "docx_fingerprint", "GOLDEN DOCX OK"):
        if marker not in golden:
            fail(f"golden DOCX regression lost marker: {marker}")
    for marker in (
        "GENDER_WORD_PAIRS",
        "DOCUMENT_ORDER",
        "docx_fingerprint",
        "GENDER GENERATION REGRESSION MATRIX OK",
    ):
        if marker not in gender_matrix:
            fail(f"gender generation regression matrix lost marker: {marker}")
    if manifest.count("sha256"):
        fail("golden DOCX manifest must contain raw hashes only, not executable metadata")
    if manifest.count(":") < 8:
        fail("golden DOCX manifest does not cover the canonical medical+diary set")


def assert_staff_profile_contract() -> None:
    settings = read("settings_mixin.py")
    main_source = read("main.py")
    window = read("window_mixin.py")
    medical_flow = read("actions_medical_flow.py")
    diary_flow = read("actions_diary_flow.py")
    regression = read("tools/staff_profile_regression.py")
    required = (
        (settings, "def _prompt_staff_profile"),
        (settings, "def _set_staff_profile"),
        (settings, '"deputy_chief"'),
        (main_source, "def _first_launch_onboarding"),
        (main_source, "app._set_desktop_intake_preference(True)"),
        (main_source, "_prompt_staff_profile(first_run=True)"),
        (window, 'text="Сотрудники"'),
        (medical_flow, "_apply_staff_profile_to_patient_data(data)"),
        (diary_flow, "doctor_name="),
        (diary_flow, "department_head_name="),
        (regression, "STAFF PROFILE REGRESSION OK"),
    )
    missing = [marker for source, marker in required if marker not in source]
    if missing:
        fail("staff profile contract is incomplete: " + ", ".join(missing))


def assert_ci_wiring() -> None:
    workflow = read(".github/workflows/windows-build.yml")
    build = read("build_exe_windows.bat")
    guard = read("tools/document_mechanics_guard.py")
    for marker in (
        "fetch-depth: 0",
        "github.event.pull_request.base.sha || github.event.before",
        "python tools/document_mechanics_guard.py",
        "python tools/production_safety_gate.py",
        "python tools/privacy_diagnostics_check.py",
        "python tools/full_patient_replay_check.py",
        "python tools/staff_profile_regression.py",
        "python tools/gender_generation_regression_matrix.py",
        "python gui_runtime_check.py",
        "python verify_built_exe.py",
        "windows_desktop_intake_e2e.ps1",
        "BUILD_WINDOWS_INSTALLER.bat",
        "windows_installer_smoke.ps1",
        "MedicalDiaryAutofill-Windows-Installer",
    ):
        if marker not in workflow:
            fail(f"Windows CI lost safety marker: {marker}")

    if '"--diff-filter=ACDMRT"' not in guard:
        fail("document mechanics guard no longer rejects protected-file deletions")

    build_has_safety_gate = (
        "python tools\\production_safety_gate.py" in build
        or "python tools/production_safety_gate.py" in build
    )
    if not build_has_safety_gate:
        fail("local Windows EXE build bypasses production safety gate")


def main() -> None:
    assert_runtime_budget()
    assert_behavior_contracts()
    assert_intake_boundary()
    assert_self_check_is_outer_only()
    assert_installer_contract()
    assert_runtime_responsiveness_contract()
    assert_privacy_and_replay_contract()
    assert_staff_profile_contract()
    assert_ci_wiring()
    print("PRODUCTION SAFETY GATE OK")


if __name__ == "__main__":
    main()
