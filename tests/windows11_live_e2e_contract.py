"""Fail-closed contract for the persistent Windows 11 live E2E contour.

This check is intentionally runnable on an ordinary CI runner. It does not claim
that a live workstation was exercised; instead it prevents the repository from
silently weakening the live contour between real workstation runs.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows11-live-e2e.yml"
PREFLIGHT = ROOT / "tools" / "windows11_live_e2e_preflight.ps1"
INSTALLER = ROOT / "tools" / "install_windows11_live_runner.ps1"
DRIVER = ROOT / "tests" / "windows11_live_gui_e2e.py"


def fail(message: str) -> None:
    raise SystemExit("WINDOWS11 LIVE E2E CONTRACT FAILED: " + message)


def require_all(text: str, snippets: tuple[str, ...], label: str) -> None:
    missing = [snippet for snippet in snippets if snippet not in text]
    if missing:
        fail(f"{label} is missing: " + ", ".join(missing))


def main() -> None:
    for path in (WORKFLOW, PREFLIGHT, INSTALLER, DRIVER):
        if not path.is_file():
            fail(f"mandatory live E2E asset is missing: {path.relative_to(ROOT)}")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    driver = DRIVER.read_text(encoding="utf-8")

    require_all(
        workflow,
        (
            "workflow_dispatch:",
            "schedule:",
            "runs-on: [self-hosted, Windows, X64, diary-filler-live-e2e, windows11-interactive]",
            "vars.WINDOWS11_LIVE_E2E_ENABLED == 'true'",
            "timeout-minutes: 120",
            "clean: true",
            "./tools/windows11_live_e2e_preflight.ps1",
            "python tools/regression_lock_check.py",
            "python tools/ci_gate_lock.py",
            "python tools/document_mechanics_guard.py",
            "python tools/production_safety_gate.py",
            "python prod_audit.py",
            "python release_check.py",
            "python tools/full_patient_replay_check.py",
            "python tests/full_user_journey_regression.py",
            "python tests/windows_e1_exhaustive_user_matrix.py",
            "python gui_runtime_check.py",
            "python tests/windows11_live_gui_e2e.py",
            "build_exe_windows.bat",
            "python verify_built_exe.py",
            "./tools/windows_desktop_intake_e2e.ps1 -AppPath ./dist/MedicalDiaryAutofill.exe",
            "BUILD_WINDOWS_INSTALLER.bat",
            "./tools/windows_installer_smoke.ps1 -InstallerPath ./dist/MedicalDiaryAutofill-Setup-1.4.25.exe",
            "Capture desktop evidence on failure",
            "Upload live E2E evidence",
        ),
        "live workflow",
    )
    if "pull_request:" in workflow:
        fail("persistent self-hosted workstation must never execute pull_request code")
    if "runs-on: windows-latest" in workflow or "runs-on: windows-202" in workflow:
        fail("live job was downgraded to an ephemeral GitHub-hosted runner")
    if "continue-on-error:" in workflow:
        fail("mandatory live contour must remain fail-closed")

    require_all(
        preflight,
        (
            "Win32_OperatingSystem",
            "ProductType",
            "BuildNumber",
            "-lt 22000",
            "SessionId",
            "PSVersionTable.PSVersion.Major",
            "OpenInputDesktop",
            "SwitchDesktop",
            "explorer.exe",
            "WINWORD.EXE",
            "Get-Printer",
            "RequireInno",
            "Inno Setup 6",
            "1280",
            "720",
            "WINDOWS11 LIVE E2E PREFLIGHT OK",
        ),
        "Windows 11 preflight",
    )

    non_comment_installer = "\n".join(
        line for line in installer.splitlines() if not line.lstrip().startswith("#")
    )
    if "--runasservice" in non_comment_installer:
        fail("runner bootstrap must not configure a Session-0 Windows service")
    require_all(
        installer,
        (
            "actions-runner-win-x64",
            "ExpectedSha256",
            "Get-FileHash -Algorithm SHA256",
            "Get-Command pwsh.exe",
            "config.cmd --unattended",
            "diary-filler-live-e2e,windows11-interactive",
            "run-interactive.cmd",
            "Start Menu\\Programs\\Startup",
            "Runner must remain signed in and unlocked",
        ),
        "runner bootstrap",
    )

    require_all(
        driver,
        (
            "CombinedMedicalDiaryApp",
            "_create_root(require_dnd=True)",
            "SetCursorPos",
            "mouse_event",
            "MOUSEEVENTF_LEFTDOWN",
            "MOUSEEVENTF_LEFTUP",
            "(*DOCUMENT_ORDER, DIARY_KIND)",
            "empty-selection-warning-via-physical-click",
            "all-eight-output-tiles-physical-toggle",
            "missing-diagnosis-visible-preflight-popup",
            "direct-sick-leave-vk-without-separate-toggle",
            "all-eight-real-production-generation",
            "_assert_generated_bundle",
            "expected 8 generated DOCX files",
        ),
        "physical GUI driver",
    )
    if "event_generate(" in driver:
        fail("live GUI driver must not substitute Tk synthetic clicks for Windows physical input")

    print(
        "WINDOWS11 LIVE E2E CONTRACT OK: trusted persistent Win11 interactive runner, "
        "OS-level input, 255 selection matrix, real 8-output bundle, packaged EXE/intake/installer evidence are locked"
    )


if __name__ == "__main__":
    main()
