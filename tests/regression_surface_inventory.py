"""Self-test the regression-lock coverage map.

This file deliberately tests categories rather than concrete Git blobs. The
blob-level protection lives in tools/regression_lock_check.py; this test makes
sure future edits cannot accidentally narrow that protection away from a major
production surface or bypass it by introducing a newly named runtime/config/data
file.
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

# These names intentionally do not match any known production naming family.
# They prove that future executable/config/data files are locked by type, not
# merely because somebody remembered to add their exact names to a list.
FUTURE_UNKNOWN_FILES_MUST_BE_LOCKED = (
    "future_runtime_module.py",
    "new_package/runtime_adapter.py",
    "scripts/future_maintenance_hook.ps1",
    "installer/future_helper.cmd",
    "config/future_generation_rules.json",
    "data/future_catalog.tsv",
    "config/future_runtime.ini",
    ".github/workflows/future-release.yaml",
)

MUST_STAY_MUTABLE_METADATA = (
    "tests/regression_lock_baseline.json",
    "tools/regression_lock_change_approval.json",
)

NON_RUNTIME_DOCUMENTATION = (
    "README.md",
    "docs/architecture.md",
)


def main() -> None:
    excluded: set[str] = set()
    missed = [path for path in MUST_BE_LOCKED if not _is_critical(path, excluded)]
    if missed:
        raise SystemExit("REGRESSION SURFACE INVENTORY FAILED: unlocked critical paths:\n" + "\n".join(missed))

    future_missed = [path for path in FUTURE_UNKNOWN_FILES_MUST_BE_LOCKED if not _is_critical(path, excluded)]
    if future_missed:
        raise SystemExit(
            "REGRESSION SURFACE INVENTORY FAILED: future runtime/config/data files can bypass the lock:\n"
            + "\n".join(future_missed)
        )

    wrongly_locked = [path for path in MUST_STAY_MUTABLE_METADATA if _is_critical(path, excluded)]
    if wrongly_locked:
        raise SystemExit(
            "REGRESSION SURFACE INVENTORY FAILED: baseline/approval metadata became self-locked:\n"
            + "\n".join(wrongly_locked)
        )

    documentation_locked = [path for path in NON_RUNTIME_DOCUMENTATION if _is_critical(path, excluded)]
    if documentation_locked:
        raise SystemExit(
            "REGRESSION SURFACE INVENTORY FAILED: ordinary documentation became production-locked:\n"
            + "\n".join(documentation_locked)
        )

    total = len(MUST_BE_LOCKED) + len(FUTURE_UNKNOWN_FILES_MUST_BE_LOCKED)
    print(
        "REGRESSION SURFACE INVENTORY OK: "
        f"{total} known/future critical-path probes are locked; ordinary docs remain mutable"
    )


if __name__ == "__main__":
    main()
