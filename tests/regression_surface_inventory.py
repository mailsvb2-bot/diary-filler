"""Self-test the regression-lock coverage map.

This file deliberately tests categories rather than concrete Git blobs. The
blob-level protection lives in tools/regression_lock_check.py; this test makes
sure future edits cannot accidentally narrow that protection away from a major
production surface.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.regression_lock_check import _is_critical

MUST_BE_LOCKED = (
    ".github/workflows/windows-build.yml",
    ".github/workflows/release.yml",
    "installer/MedicalDiaryAutofill.iss",
    "main.py",
    "startup.py",
    "actions_medical_flow.py",
    "actions_diary_flow.py",
    "medical_service.py",
    "medical_parser.py",
    "medical_renderer_primary.py",
    "medical_gender.py",
    "diary_batch.py",
    "diary_service.py",
    "diary_writer_entries.py",
    "embedded_templates.py",
    "dialog_document_details.py",
    "files_mixin.py",
    "settings_mixin.py",
    "shared_dates.py",
    "shared_gender.py",
    "dnd_contract_check.py",
    "gui_runtime_check.py",
    "prod_audit.py",
    "release_check.py",
    "safety_integrity_check.py",
    "smoke_combined_part04_medical_generation.py",
    "tests/golden_docx_manifest.json",
    "tests/desktop_intake_contract_check.py",
    "tests/intake_lifecycle_regression.py",
    "tools/document_mechanics_guard.py",
    "tools/full_patient_replay_check.py",
    "tools/golden_docx_regression.py",
    "tools/windows_desktop_intake_e2e.ps1",
    "tools/windows_installer_smoke.ps1",
    "tools/regression_lock_check.py",
    "tools/ci_gate_lock.py",
    "tools/run_regression_suite.py",
    "verify_built_exe.py",
    "build_exe_windows.bat",
    "BUILD_WINDOWS_INSTALLER.bat",
    "requirements_build.txt",
    "pyproject.toml",
    "version_info.txt",
)

MUST_STAY_MUTABLE_METADATA = (
    "tests/regression_lock_baseline.json",
    "tools/regression_lock_change_approval.json",
)


def main() -> None:
    excluded: set[str] = set()
    missed = [path for path in MUST_BE_LOCKED if not _is_critical(path, excluded)]
    if missed:
        raise SystemExit("REGRESSION SURFACE INVENTORY FAILED: unlocked critical paths:\n" + "\n".join(missed))

    wrongly_locked = [path for path in MUST_STAY_MUTABLE_METADATA if _is_critical(path, excluded)]
    if wrongly_locked:
        raise SystemExit(
            "REGRESSION SURFACE INVENTORY FAILED: baseline/approval metadata became self-locked:\n"
            + "\n".join(wrongly_locked)
        )

    print(f"REGRESSION SURFACE INVENTORY OK: {len(MUST_BE_LOCKED)} representative critical paths are locked")


if __name__ == "__main__":
    main()
