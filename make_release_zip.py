"""Create a clean source release zip with a stable production root folder."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release"
OUTPUT = RELEASE_DIR / "MedicalDiaryAutofill_PRODUCTION_SOURCE.zip"
ARCHIVE_ROOT = "MedicalDiaryAutofill_PRODUCTION"
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", ".venv_build", ".venv_runtime", "__pycache__",
    "build", "dist", ".pytest_cache", ".ruff_cache", "release", ".vscode", ".idea",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".spec", ".bak"}
EXCLUDE_NAMES = {"startup_error.log", ".DS_Store", "Thumbs.db"}


def should_include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    # Exclude generated smoke/run folders by any ancestor component. The old
    # check only tested ``path.is_dir()``, but this function is called for files
    # during archive creation, so files inside ``test_run_combined`` could leak
    # into a source zip if make_release_zip.py was run directly after smoke tests.
    if any(part.startswith("test_run") or part.endswith("_run") for part in rel.parts):
        return False
    if path.name in EXCLUDE_NAMES:
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    if path.name.startswith("ОТЧЁТ_") and path.suffix.lower() == ".txt":
        return False
    if path.is_file() and (path.name.endswith(".log") or path.name.endswith(".tmp")):
        return False
    return True


def main() -> None:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()
    files = [path for path in ROOT.rglob("*") if path.is_file() and should_include(path)]
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(files, key=lambda p: str(p.relative_to(ROOT)).lower()):
            arcname = Path(ARCHIVE_ROOT) / path.relative_to(ROOT)
            zf.write(path, arcname.as_posix())
    print(OUTPUT)


if __name__ == "__main__":
    main()
