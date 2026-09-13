"""Fail CI when infrastructure work touches the working document mechanics.

This guard intentionally protects source ownership, not just behavior observed by
a test. Production-safety work must move outward instead of editing the parser,
renderers, popup/data flow or medical/diary generation routes.

An explicit mechanics task may carry one repository approval file, but that
approval is fail-closed: it is bound to one exact base commit and the exact Git
blob of every protected file. Any later protected edit, extra protected path,
deleted file, or different base commit is rejected automatically.
"""
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_PATH = ROOT / "tools" / "document_mechanics_change_approval.json"

# Deliberately broad. Safety/support/installer work has no reason to edit these
# paths. A future explicit document-mechanics task must be reviewed separately.
PROTECTED_PATTERNS = (
    "actions_creation*.py",
    "actions_diary_flow.py",
    "actions_medical_flow.py",
    "actions_navigation.py",
    "actions_selection.py",
    "actions_template_checks.py",
    "actions_ui_state.py",
    "app.py",
    "app_config.py",
    "app_initialization.py",
    "diagnosis_widget.py",
    "dialog_*.py",
    "files_mixin.py",
    "icd10_*.py",
    "medical_*.py",
    "diary_*.py",
    "shared_dates.py",
    "shared_paths.py",
    "embedded_templates.py",
    "layout_action_bar.py",
    "layout_checklist.py",
    "layout_sources.py",
)


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace"
    ).strip()


def _base_ref() -> str:
    explicit = os.environ.get("DOCUMENT_MECHANICS_BASE_SHA", "").strip()
    if explicit:
        _git("cat-file", "-e", f"{explicit}^{{commit}}")
        return explicit

    base_branch = os.environ.get("GITHUB_BASE_REF", "").strip()
    if base_branch:
        remote = f"origin/{base_branch}"
        _git("cat-file", "-e", f"{remote}^{{commit}}")
        return _git("merge-base", "HEAD", remote)

    return _git("rev-parse", "HEAD^1")


def _is_protected(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if "/" in normalized:
        return False
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in PROTECTED_PATTERNS)


def _exact_approval(base: str, protected: list[str]) -> tuple[bool, str]:
    if not APPROVAL_PATH.exists():
        return False, ""
    try:
        approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, ""

    if approval.get("schema_version") != 1 or approval.get("base_sha") != base:
        return False, ""
    approved_blobs = approval.get("approved_blobs")
    if not isinstance(approved_blobs, dict):
        return False, ""
    normalized_approved = {str(path).replace("\\", "/"): str(blob) for path, blob in approved_blobs.items()}
    if set(normalized_approved) != set(protected):
        return False, ""

    for path in protected:
        candidate = ROOT / path
        if not candidate.exists() or not candidate.is_file():
            return False, ""
        try:
            actual_blob = _git("rev-parse", f"HEAD:{path}")
        except subprocess.CalledProcessError:
            return False, ""
        if actual_blob != normalized_approved[path]:
            return False, ""

    return True, str(approval.get("reason") or "explicit exact-blob approval")


def main() -> None:
    try:
        base = _base_ref()
        changed = [
            line.strip().replace("\\", "/")
            for line in _git("diff", "--name-only", "--diff-filter=ACDMRT", base, "HEAD").splitlines()
            if line.strip()
        ]
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(f"DOCUMENT MECHANICS GUARD ERROR: cannot establish git base: {exc}")

    protected = sorted(path for path in changed if _is_protected(path))
    if protected:
        approved, reason = _exact_approval(base, protected)
        if not approved:
            raise SystemExit(
                "DOCUMENT MECHANICS GUARD FAILED. Safety/support work modified protected files:\n"
                + "\n".join(f"- {path}" for path in protected)
                + "\nMove the change outside the existing document mechanics, or provide an exact-base/exact-blob approval for an explicit mechanics task."
            )
        print(
            "DOCUMENT MECHANICS GUARD OK: exact protected mechanics change approved; "
            f"base={base}; files={', '.join(protected)}; reason={reason}"
        )
        return

    print(f"DOCUMENT MECHANICS GUARD OK: {len(changed)} changed path(s), protected mechanics untouched")


if __name__ == "__main__":
    main()
