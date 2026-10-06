"""Lock the complete production-journey verification topology.

This is intentionally a topology/continuity contract, not a second generator.
Behavior remains exercised by the existing production-path regressions and
Windows E2E scripts named below.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    path = ROOT / rel
    assert path.is_file(), f"missing production-journey evidence: {rel}"
    return path.read_text(encoding="utf-8", errors="replace")


def _require(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    assert not missing, f"{label} lost production-journey coverage: {missing}"


def main() -> None:
    windows = _read(".github/workflows/windows-build.yml")
    live_core = _read(".github/workflows/windows-live-e2e-core.yml")
    live_plan = _read(".github/workflows/windows-live-e2e.yml")
    full_journey = _read("tests/full_user_journey_regression.py")
    matrix = _read("tests/windows_e1_exhaustive_user_matrix.py")
    live_gui = _read("tests/windows_live_gui_e2e.py")
    intake = _read("tools/windows_desktop_intake_e2e.ps1")
    installer = _read("tools/windows_installer_smoke.ps1")
    registry = _read("tests/patient_registry_regression.py")
    replay = _read("tools/full_patient_replay_check.py")
    license_off = _read("tests/licensing_disabled_mode_contract.py")

    # J1: ordinary primary -> prompts/preflight -> selected outputs -> save/retry.
    _require(full_journey, (
        "assert_missing_primary_stops_before_prompts",
        "assert_full_success_commits_all_selected",
        "assert_partial_retry_does_not_duplicate_medical",
        "assert_double_click_guard_suppresses_identical_second_action",
    ), "J1 ordinary generation")

    # J2: every output selection through the real production orchestrator.
    _require(matrix, (
        "2^8 - 1 = 255",
        "app.create_selected_outputs()",
        "assert count == 255",
    ), "J2 exhaustive output selection")

    # J3: real parser/renderers -> canonical medical+diary DOCX semantics.
    _require(replay, (
        "smoke_test.py",
        "verify_golden",
        "FULL PATIENT REPLAY OK",
        "snapshot_diary_output",
        "дневники.docx",
    ), "J3 real DOCX replay")

    # J4: physical GUI -> visible preflight -> all 8 outputs -> real DOCX.
    _require(live_gui, (
        "_physical_click(root, save_canvas)",
        "missing-diagnosis-visible-preflight-popup",
        "direct-sick-leave-vk-without-separate-toggle",
        "all-eight-real-production-generation",
        "expected 8 generated DOCX files",
    ), "J4 physical GUI generation")

    # J5: closed GUI -> Desktop/OneDrive-known Desktop intake -> watcher -> visible GUI
    # -> primary moved into a patient subfolder.
    _require(intake, (
        "Resolve-DesktopPath",
        "User Shell Folders",
        "Выписанные пациенты",
        "--intake-agent",
        "--intake-primary",
        "primary DOCX moved into patient subfolder",
        "WINDOWS DESKTOP INTAKE AUTOLAUNCH E2E OK",
    ), "J5 packaged intake")

    # J6: installer -> installed onedir -> watcher -> dropped primary -> visible GUI
    # -> preserved patient folder -> uninstall cleanup.
    lifecycle = _read("tests/intake_lifecycle_regression.py")

    _require(lifecycle, (
        "assert_background_agent_spawn_stays_hidden",
        "assert_gui_healthcheck_restarts_dead_agent",
        "_desktop_schedule_agent_health(app)",
    ), "J5b watcher invisibility and crash recovery")

    _require(installer, (
        "Installed application startup probe",
        "INSTALLED INTAKE drop-to-visible latency",
        "Installed watcher did not open a visible GUI for the dropped primary DOCX",
        "Installed watcher GUI did not move the primary DOCX into a patient subfolder",
        "Uninstaller removed Desktop\\Выписанные пациенты",
        "Uninstaller removed a user-owned file from Desktop\\Выписанные пациенты",
        "WINDOWS INSTALLER FAST ONEDIR WATCHER BOOTSTRAP AND UNINSTALL SMOKE OK",
    ), "J6 install/intake/uninstall")

    # J7: My Patients -> scan -> click=open / hold=load -> sick leave/RVK timelines
    # -> persistent summary/tray wiring.
    _require(registry, (
        "_assert_real_docx_registry_ingestion",
        "_assert_patient_primary_click_hold_contract",
        "_assert_vk_wednesday_schedule",
        "_assert_discharge_stays_admission_based",
        "PATIENT_SUMMARY_TRAY_ARGUMENT",
        "install_patient_summary_autostart()",
        "minimize_to_tray",
        "_prepare_registry_rvk_act",
        "Подготовить ВК по больничному на",
    ), "J7 My Patients")

    # J8: licensing implementation remains present, but the current product mode
    # cannot gate startup or generation.
    _require(license_off, (
        "_assert_implementation_is_preserved",
        "_assert_unlicensed_runtime_cannot_be_resurrected_by_environment",
        "_assert_disabled_mode_never_blocks_user_paths",
    ), "J8 unlicensed product mode")

    # Mandatory hosted Windows CI must execute every non-physical contour.
    _require(windows, (
        "python tests/licensing_disabled_mode_contract.py",
        "python tools/full_patient_replay_check.py",
        "python tests/full_user_journey_regression.py",
        "python tests/patient_registry_regression.py",
        "python tests/windows_e1_exhaustive_user_matrix.py",
        "windows_desktop_intake_e2e.ps1",
        "windows_installer_smoke.ps1",
    ), "hosted Windows CI")

    # Physical evidence remains a distinct gate and must never be confused with
    # hosted CI. Both Win10 and Win11 targets must stay explicit.
    _require(live_plan, (
        "windows10-interactive",
        "windows11-interactive",
        "NO PHYSICAL LIVE E2E EVIDENCE",
        "github.ref == 'refs/heads/main'",
    ), "physical Windows plan")
    _require(live_core, (
        "Run physical-input Windows live GUI E2E",
        "python tests/windows_live_gui_e2e.py",
        "Run packaged desktop intake auto-launch E2E",
        "Smoke installed and uninstalled application",
    ), "physical Windows core")

    print(
        "PRODUCTION JOURNEYS CONTRACT OK: J1 ordinary generation; J2 all 255 selections; "
        "J3 real DOCX replay; J4 physical GUI generation; J5 packaged intake; "
        "J6 install/intake/uninstall; J7 My Patients; J8 licensing-off mode; "
        "hosted and physical Windows evidence topology locked"
    )


if __name__ == "__main__":
    main()
