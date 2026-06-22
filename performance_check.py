"""Performance guard for MedicalDiaryAutofill startup imports.

This check is intentionally small and stdlib-only. It protects the UI startup
path from reintroducing heavy DOCX/printer/ICD imports before the first user
operation.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FORBIDDEN_EAGER_MODULES = {
    "docx",
    "embedded_templates",
    "medical_documents",
    "medical_service",
    "medical_renderer",
    "medical_docx_blocks",
    "medical_docx_editor",
    "diary_filler",
    "diary_batch",
    "icd10_f",
    "printer_support",
}


def startup_import_probe_code() -> str:
    return """
import app, sys
forbidden = sorted(name for name in {forbidden!r} if name in sys.modules)
if forbidden:
    raise SystemExit('Heavy modules imported during app startup: ' + ', '.join(forbidden))
print('PERFORMANCE CHECK OK')
""".format(forbidden=FORBIDDEN_EAGER_MODULES)


def main() -> None:
    # Keep this check isolated from the release_check.py process: the release gate
    # imports audit/test helpers before reaching the performance step, so checking
    # sys.modules in-process would be meaningless. A timeout prevents CI/terminal
    # runs from hanging forever if a future import starts a GUI/event-loop or blocks
    # on a platform API.
    subprocess.run([sys.executable, "-c", startup_import_probe_code()], cwd=ROOT, check=True, timeout=30)


if __name__ == "__main__":
    main()
