"""Repository-wide regression lock for the known-good production surface.

The lock compares every critical tracked file with a tested baseline commit. Any
critical change, addition, or deletion fails closed unless an explicit approval
is bound to the current baseline and to the exact candidate Git blobs.

After an approved candidate has passed the full CI, advance
``tests/regression_lock_baseline.json`` in a separate metadata-only commit to
the exact tested candidate commit and remove the temporary approval file.
"""
from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "tests" / "regression_lock_baseline.json"
APPROVAL_PATH = ROOT / "tools" / "regression_lock_change_approval.json"

CRITICAL_PATTERNS = (
    ".github/workflows/*.yml",
    "installer/*.iss",
    "tools/*.py",
    "tools/*.ps1",
    "tests/*.py",
    "tests/golden_docx_manifest.json",
    "actions_*.py",
    "app*.py",
    "diagnosis_widget.py",
    "dialog_*.py",
    "diary_*.py",
    "dnd_*.py",
    "embedded_templates.py",
    "files_mixin.py",
    "gui_runtime_check.py",
    "icd10_*.py",
    "layout_*.py",
    "main.py",
    "medical_*.py",
    "printer_*.py",
    "prod_audit.py",
    "release_check.py",
    "safety_integrity_check.py",
    "settings_mixin.py",
    "shared_*.py",
    "smoke*.py",
    "startup.py",
    "ui_*.py",
    "verify_built_exe.py",
    "window_mixin.py",
    "widgets_mixin.py",
    "build_exe_windows.bat",
    "BUILD_WINDOWS_INSTALLER.bat",
    "make_release_zip.py",
    "requirements*.txt",
    "pyproject.toml",
    "version_info.txt",
)

ALWAYS_EXCLUDED = {
    "tests/regression_lock_baseline.json",
    "tools/regression_lock_change_approval.json",
}

DEFAULT_REQUIRED_EVIDENCE = {
    "document_mechanics_guard",
    "full_patient_replay",
    "golden_docx",
    "staff_profile_regression",
    "gender_generation_matrix",
    "desktop_intake_contract",
    "intake_lifecycle_regression",
    "packaged_desktop_intake_e2e",
    "installer_uninstall_smoke",
}


def _git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _load_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"REGRESSION LOCK FAILED: invalid baseline config: {exc}")
    if data.get("schema_version") != 1:
        raise SystemExit("REGRESSION LOCK FAILED: unsupported baseline schema")
    baseline = str(data.get("baseline_ref") or "").strip()
    if not baseline:
        raise SystemExit("REGRESSION LOCK FAILED: baseline_ref is empty")
    return data


def _is_critical(path: str, extra_excluded: set[str]) -> bool:
    path = path.replace("\\", "/")
    if path in ALWAYS_EXCLUDED or path in extra_excluded:
        return False
    return any(fnmatch.fnmatch(path, pattern) for pattern in CRITICAL_PATTERNS)


def _tree_files(ref: str) -> set[str]:
    output = _git("ls-tree", "-r", "--name-only", ref)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _current_files() -> set[str]:
    output = _git("ls-files")
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _blob(ref: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", f"{ref}:{path}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _exact_approval(baseline: str, mismatches: dict[str, tuple[str | None, str | None]], required: set[str]) -> tuple[bool, str]:
    if not APPROVAL_PATH.exists():
        return False, ""
    try:
        approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, ""
    if approval.get("schema_version") != 1:
        return False, ""
    if str(approval.get("baseline_ref") or "").strip() != baseline:
        return False, ""
    reason = str(approval.get("reason") or "").strip()
    if len(reason) < 12:
        return False, ""
    evidence = {str(item) for item in approval.get("required_evidence", [])}
    if not required.issubset(evidence):
        return False, ""
    approved = approval.get("approved_blobs")
    if not isinstance(approved, dict) or set(approved) != set(mismatches):
        return False, ""
    for path, (_old_blob, new_blob) in mismatches.items():
        expected = "<deleted>" if new_blob is None else new_blob
        if str(approved.get(path)) != expected:
            return False, ""
    return True, reason


def main() -> None:
    config = _load_config()
    baseline = str(config["baseline_ref"]).strip()
    try:
        _git("cat-file", "-e", f"{baseline}^{{commit}}")
    except RuntimeError as exc:
        raise SystemExit(f"REGRESSION LOCK FAILED: baseline commit unavailable: {exc}")

    extra_excluded = {str(item).replace("\\", "/") for item in config.get("excluded_paths", [])}
    required = set(DEFAULT_REQUIRED_EVIDENCE)
    required.update(str(item) for item in config.get("required_approval_evidence", []))

    baseline_files = _tree_files(baseline)
    current_files = _current_files()
    critical_paths = sorted(
        path
        for path in baseline_files | current_files
        if _is_critical(path, extra_excluded)
    )
    if not critical_paths:
        raise SystemExit("REGRESSION LOCK FAILED: critical surface is empty")

    mismatches: dict[str, tuple[str | None, str | None]] = {}
    for path in critical_paths:
        old_blob = _blob(baseline, path)
        new_blob = _blob("HEAD", path)
        if old_blob != new_blob:
            mismatches[path] = (old_blob, new_blob)

    if mismatches:
        approved, reason = _exact_approval(baseline, mismatches, required)
        if not approved:
            details = []
            for path, (old_blob, new_blob) in mismatches.items():
                status = "added" if old_blob is None else "deleted" if new_blob is None else "changed"
                details.append(f"- {status}: {path}")
            raise SystemExit(
                "REGRESSION LOCK FAILED: known-good production/test surface drifted from "
                f"{baseline}.\n"
                + "\n".join(details)
                + "\nProvide an exact temporary tools/regression_lock_change_approval.json, run every required regression, then advance the baseline in a separate commit."
            )
        print(
            "REGRESSION LOCK OK: exact candidate drift explicitly approved; "
            f"baseline={baseline}; changed={len(mismatches)}; reason={reason}"
        )
        return

    if APPROVAL_PATH.exists():
        raise SystemExit("REGRESSION LOCK FAILED: stale approval file exists but there is no locked-surface drift")

    print(f"REGRESSION LOCK OK: {len(critical_paths)} critical files match baseline {baseline}")


if __name__ == "__main__":
    main()
