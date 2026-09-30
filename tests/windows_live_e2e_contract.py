"""Fail-closed contract for the Windows 10 + Windows 11 live E2E matrix."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / ".github" / "workflows" / "windows-live-e2e.yml"
CORE = ROOT / ".github" / "workflows" / "windows-live-e2e-core.yml"
PREFLIGHT = ROOT / "tools" / "windows_live_e2e_preflight.ps1"
INSTALLER = ROOT / "tools" / "install_windows_live_runner.ps1"
CMD_INSTALLER = ROOT / "tools" / "install_windows_live_runner.cmd"
DRIVER = ROOT / "tests" / "windows_live_gui_e2e.py"
WIN11_PREFLIGHT_COMPAT = ROOT / "tools" / "windows11_live_e2e_preflight.ps1"
WIN11_INSTALLER_COMPAT = ROOT / "tools" / "install_windows11_live_runner.ps1"
WIN11_DRIVER_COMPAT = ROOT / "tests" / "windows11_live_gui_e2e.py"


def fail(message: str) -> None:
    raise SystemExit("WINDOWS LIVE E2E CONTRACT FAILED: " + message)


def require_all(text: str, snippets: tuple[str, ...], label: str) -> None:
    missing = [snippet for snippet in snippets if snippet not in text]
    if missing:
        fail(f"{label} is missing: " + ", ".join(missing))


def main() -> None:
    for path in (
        MATRIX, CORE, PREFLIGHT, INSTALLER, CMD_INSTALLER, DRIVER,
        WIN11_PREFLIGHT_COMPAT, WIN11_INSTALLER_COMPAT, WIN11_DRIVER_COMPAT,
    ):
        if not path.is_file():
            fail(f"mandatory live E2E asset is missing: {path.relative_to(ROOT)}")

    matrix = MATRIX.read_text(encoding="utf-8")
    core = CORE.read_text(encoding="utf-8")
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    cmd_installer = CMD_INSTALLER.read_text(encoding="utf-8")
    driver = DRIVER.read_text(encoding="utf-8")

    require_all(
        matrix,
        (
            "workflow_dispatch:",
            "default: both",
            "- both",
            "- windows10",
            "- windows11",
            "schedule:",
            "WINDOWS10_LIVE_E2E_ENABLED",
            "WINDOWS11_LIVE_E2E_ENABLED",
            '"target_os": "windows10"',
            '"runner_label": "windows10-interactive"',
            '"target_os": "windows11"',
            '"runner_label": "windows11-interactive"',
            "github.ref == 'refs/heads/main'",
            "strategy:",
            "fail-fast: false",
            "max-parallel: 2",
            r"matrix: ${{ fromJSON(needs.plan.outputs.matrix) }}",
            r"name: Live E2E / ${{ matrix.artifact_suffix }}",
            "uses: ./.github/workflows/windows-live-e2e-core.yml",
            r"target_os: ${{ matrix.target_os }}",
            r"runner_label: ${{ matrix.runner_label }}",
        ),
        "two-OS matrix workflow",
    )
    if matrix.count('"target_os": "windows10"') != 1:
        fail("matrix must define exactly one Windows 10 live configuration")
    if matrix.count('"target_os": "windows11"') != 1:
        fail("matrix must define exactly one Windows 11 live configuration")
    if "pull_request:" in matrix:
        fail("physical self-hosted matrix must never execute pull_request code")
    if "windows-latest" in matrix:
        fail("live matrix must not downgrade a physical OS row to windows-latest")

    require_all(
        core,
        (
            "workflow_call:",
            "- self-hosted",
            "- Windows",
            "- X64",
            "- diary-filler-live-e2e",
            r"- ${{ inputs.runner_label }}",
            "timeout-minutes: 120",
            r'if ("${{ github.ref }}" -ne "refs/heads/main")',
            '"windows10" = "windows10-interactive"',
            '"windows11" = "windows11-interactive"',
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "clean: true",
            r'./tools/windows_live_e2e_preflight.ps1 -TargetOs "${{ inputs.target_os }}"',
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
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
            "python tests/windows_live_gui_e2e.py",
            "build_exe_windows.bat",
            "python verify_built_exe.py",
            "./tools/windows_desktop_intake_e2e.ps1 -AppPath ./dist/MedicalDiaryAutofill.exe",
            "BUILD_WINDOWS_INSTALLER.bat",
            "./tools/windows_installer_smoke.ps1 -InstallerPath ./dist/MedicalDiaryAutofill-Setup-1.4.25.exe",
            "Capture desktop evidence on failure",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            r"MedicalDiaryAutofill-${{ inputs.target_os }}-Live-E2E-${{ github.run_id }}",
        ),
        "shared physical live core",
    )
    for forbidden in ("pull_request:", "runs-on: windows-latest", "continue-on-error:"):
        if forbidden in core:
            fail(f"shared live workflow contains forbidden construct: {forbidden}")

    require_all(
        preflight,
        (
            '[ValidateSet("windows10", "windows11")]',
            'if ($TargetOs -eq "windows10")',
            "$build -lt 19041 -or $build -ge 22000",
            'elseif ($TargetOs -eq "windows11")',
            "$build -lt 22000",
            "Win32_OperatingSystem",
            "ProductType",
            "SessionId",
            "OpenInputDesktop",
            "SwitchDesktop",
            "explorer.exe",
            "WINWORD.EXE",
            "Get-Printer",
            "Inno Setup 6",
            "target_os = $TargetOs",
            "WINDOWS LIVE E2E PREFLIGHT OK",
        ),
        "Windows 10/11 preflight",
    )

    non_comment_installer = "\n".join(
        line for line in installer.splitlines() if not line.lstrip().startswith("#")
    )
    if "--runasservice" in non_comment_installer:
        fail("runner bootstrap must not configure a Session-0 Windows service")
    require_all(
        installer,
        (
            '[ValidateSet("windows10", "windows11")]',
            '[version]"2.327.1"',
            "actions-runner-win-x64",
            "ExpectedSha256",
            "Get-FileHash -Algorithm SHA256",
            '"windows10-interactive"',
            '"windows11-interactive"',
            "config.cmd --unattended",
            "diary-filler-live-e2e",
            "run-interactive.cmd",
            "Runner must remain signed in and unlocked",
        ),
        "shared runner bootstrap",
    )

    require_all(
        cmd_installer,
        (
            "@echo off",
            "setlocal EnableExtensions DisableDelayedExpansion",
            "windows10",
            "windows11",
            "where pwsh.exe",
            "where curl.exe",
            "install_windows_live_runner.ps1",
            "Paste GitHub runner registration token and press Enter:",
            '-RunnerVersion "2.337.0"',
            '-ExpectedSha256 "1150692afa94e71f872017e254ea55b6eece1eece3fe7e3a6d4c93d0a1b85cfc"',
            '-TargetOs "%TARGET_OS%"',
            "set \"RUNNER_TOKEN=\"",
        ),
        "CMD runner bootstrap",
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

    require_all(
        WIN11_PREFLIGHT_COMPAT.read_text(encoding="utf-8"),
        ("windows_live_e2e_preflight.ps1", "-TargetOs windows11"),
        "Win11 preflight compatibility wrapper",
    )
    require_all(
        WIN11_INSTALLER_COMPAT.read_text(encoding="utf-8"),
        ("install_windows_live_runner.ps1", "-TargetOs windows11"),
        "Win11 installer compatibility wrapper",
    )
    require_all(
        WIN11_DRIVER_COMPAT.read_text(encoding="utf-8"),
        ("windows_live_gui_e2e.py", "runpy.run_path"),
        "Win11 GUI compatibility wrapper",
    )

    print(
        "WINDOWS LIVE E2E CONTRACT OK: one fail-fast=false matrix emits independent "
        "Win10 and Win11 physical jobs sharing the same trusted-main live core"
    )


if __name__ == "__main__":
    main()
