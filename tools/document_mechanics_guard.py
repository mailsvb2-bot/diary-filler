"""Fail CI when infrastructure work touches the working document mechanics.

This guard intentionally protects source ownership, not just behavior observed by
a test.  Production-safety work must move outward instead of editing the parser,
renderers, popup/data flow or medical/diary generation routes.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

PROTECTED_PATTERNS = (
    "actions_creation_orchestrator.py",
    "actions_diary_flow.py",
    "actions_medical_flow.py",
    "dialog_*.py",
    "files_mixin.py",
    "medical_documents.py",
    "medical_formatting.py",
    "medical_paths.py",
    "medical_service.py",
    "medical_parser*.py",
    "medical_renderer*.py",
    "medical_docx_editor*.py",
    "diary_batch.py",
    "diary_constants.py",
    "diary_dates.py",
    "diary_schedule.py",
    "diary_service.py",
    "diary_text_parser.py",
    "diary_text_selection.py",
    "diary_writer*.py",
    "diary_table*.py",
    "embedded_templates.py",
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


def main() -> None:
    try:
        base = _base_ref()
        changed = [
            line.strip().replace("\\", "/")
            for line in _git("diff", "--name-only", "--diff-filter=ACMRT", base, "HEAD").splitlines()
            if line.strip()
        ]
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(f"DOCUMENT MECHANICS GUARD ERROR: cannot establish git base: {exc}")

    protected = sorted(path for path in changed if _is_protected(path))
    if protected:
        raise SystemExit(
            "DOCUMENT MECHANICS GUARD FAILED. Safety/support work modified protected files:\n"
            + "\n".join(f"- {path}" for path in protected)
            + "\nMove the change outside the existing document mechanics."
        )

    print(f"DOCUMENT MECHANICS GUARD OK: {len(changed)} changed path(s), protected mechanics untouched")


if __name__ == "__main__":
    main()
