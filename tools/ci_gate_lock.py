"""Semantic lock for mandatory CI/release regression gates.

This catches a dangerous class of regression where tests still exist in the
repository but are removed, reordered past packaging, or skipped by an official
release workflow.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_WORKFLOW = ROOT / ".github" / "workflows" / "windows-build.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"

WINDOWS_REQUIRED_IN_ORDER = (
    "python tools/regression_lock_check.py",
    "python tools/ci_gate_lock.py",
    "python tests/regression_surface_inventory.py",
    "python tools/document_mechanics_guard.py",
    "python tools/production_safety_gate.py",
    "python tools/privacy_diagnostics_check.py",
    "python prod_audit.py",
    "python release_check.py",
    "python tools/full_patient_replay_check.py",
    "python tools/staff_profile_regression.py",
    "python tools/gender_generation_regression_matrix.py",
    "python tests/desktop_intake_contract_check.py",
    "python tests/intake_lifecycle_regression.py",
    "python gui_runtime_check.py",
    "build_exe_windows.bat",
    "python verify_built_exe.py",
    "./tools/windows_desktop_intake_e2e.ps1 -AppPath ./dist/MedicalDiaryAutofill.exe",
    "BUILD_WINDOWS_INSTALLER.bat",
    "./tools/windows_installer_smoke.ps1 -InstallerPath ./dist/MedicalDiaryAutofill-Setup-1.4.4.exe",
)

RELEASE_REQUIRED_IN_ORDER = (
    "python tools/regression_lock_check.py",
    "python tools/ci_gate_lock.py",
    "python tests/regression_surface_inventory.py",
    "python tools/production_safety_gate.py",
    "python tools/privacy_diagnostics_check.py",
    "python prod_audit.py",
    "python release_check.py",
    "python tools/full_patient_replay_check.py",
    "python tools/staff_profile_regression.py",
    "python tools/gender_generation_regression_matrix.py",
    "python tests/desktop_intake_contract_check.py",
    "python tests/intake_lifecycle_regression.py",
    "python gui_runtime_check.py",
    "build_exe_windows.bat",
    "signtool sign",
    "python verify_built_exe.py",
    "./tools/windows_desktop_intake_e2e.ps1 -AppPath ./dist/MedicalDiaryAutofill.exe",
    "python make_release_zip.py",
)

REQUIRED_REPOSITORY_FILES = (
    "tests/golden_docx_manifest.json",
    "tests/regression_lock_baseline.json",
    "tests/regression_surface_inventory.py",
    "tests/desktop_intake_contract_check.py",
    "tests/intake_lifecycle_regression.py",
    "tools/document_mechanics_guard.py",
    "tools/full_patient_replay_check.py",
    "tools/golden_docx_regression.py",
    "tools/staff_profile_regression.py",
    "tools/gender_generation_regression_matrix.py",
    "tools/windows_desktop_intake_e2e.ps1",
    "tools/windows_installer_smoke.ps1",
    "tools/regression_lock_check.py",
    "tools/ci_gate_lock.py",
    "tools/run_regression_suite.py",
)


def _require_order(text: str, snippets: tuple[str, ...], label: str) -> None:
    cursor = -1
    for snippet in snippets:
        position = text.find(snippet, cursor + 1)
        if position < 0:
            raise SystemExit(f"CI GATE LOCK FAILED: {label} is missing mandatory gate: {snippet}")
        if position <= cursor:
            raise SystemExit(f"CI GATE LOCK FAILED: {label} gate order changed around: {snippet}")
        cursor = position


def main() -> None:
    for relative in REQUIRED_REPOSITORY_FILES:
        if not (ROOT / relative).is_file():
            raise SystemExit(f"CI GATE LOCK FAILED: mandatory regression asset missing: {relative}")

    windows = WINDOWS_WORKFLOW.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    for required in ("pull_request:", "workflow_dispatch:", "branches: [main, master]", "fetch-depth: 0"):
        if required not in windows:
            raise SystemExit(f"CI GATE LOCK FAILED: Windows workflow lost trigger/history contract: {required}")
    _require_order(windows, WINDOWS_REQUIRED_IN_ORDER, "Windows workflow")

    if windows.count("if-no-files-found: error") < 5:
        raise SystemExit("CI GATE LOCK FAILED: Windows workflow artifacts are no longer fail-closed")

    for required in ("workflow_dispatch:", "Checkout exact release tag", "fetch-depth: 0", "MEDICAL_AUTOFILL_REQUIRE_SIGNED_EXE"):
        if required not in release:
            raise SystemExit(f"CI GATE LOCK FAILED: release workflow lost release-safety contract: {required}")
    _require_order(release, RELEASE_REQUIRED_IN_ORDER, "release workflow")

    print("CI GATE LOCK OK: mandatory PR/main/release regression topology is intact")


if __name__ == "__main__":
    main()
