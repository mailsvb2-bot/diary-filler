"""Production release gate for MedicalDiaryAutofill.

Runs the checks that must be green before a source archive or Windows EXE is
published. The script deliberately uses only the standard library so it can run
before optional dev dependencies are installed.
"""

from __future__ import annotations

import compileall
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = [
    "main.py",
    "medical_documents.py",
    "diary_filler.py",
    "printer_support.py",
    "icd10_f.py",
    "embedded_templates.py",
    "requirements.txt",
    "requirements_build.txt",
    "README.md",
    "FIX_REPORT.md",
    "version_info.txt",
    "LAUNCH_CHECKLIST.md",
    "PROD_READY_AUDIT_REPORT.md",
    "prod_audit.py",
    "dnd_contract_check.py",
    "performance_check.py",
    ".github/workflows/windows-build.yml",
    ".gitattributes",
]
FORBIDDEN_DIR_NAMES = {"__pycache__", "build", "dist", ".pytest_cache", ".vscode", ".idea"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".spec", ".bak"}
IGNORED_DIR_NAMES = {".git", ".venv", "venv", ".venv_build", ".venv_runtime", "release", ".ruff_cache"}


def _project_python_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(ROOT.glob("*.py"))
        if path.name != Path(__file__).name
    )


def _print_step(title: str) -> None:
    print(f"\n== {title} ==")


def _run(cmd: list[str], *, timeout: int = 120) -> None:
    print("$ " + " ".join(cmd), flush=True)
    # Let the child inherit stdout/stderr. Capturing output can hang when a
    # checked command opens helper processes that inherit the pipe; direct output
    # is also friendlier for a developer running release_check.bat manually.
    proc = subprocess.Popen(cmd, cwd=ROOT)
    elapsed = 0
    try:
        while True:
            try:
                proc.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                elapsed += 1
                if elapsed % 5 == 0:
                    print(f"... still running ({elapsed}s): {' '.join(cmd)}", flush=True)
                if elapsed >= timeout:
                    proc.kill()
                    raise SystemExit(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    finally:
        if proc.poll() is None:
            proc.kill()


def _remove_generated_outputs() -> None:
    for child in ROOT.iterdir():
        if child.is_dir() and (child.name.startswith("test_run") or child.name.endswith("_run")):
            shutil.rmtree(child, ignore_errors=True)
    for pycache in ROOT.rglob("__pycache__"):
        if any(part in IGNORED_DIR_NAMES for part in pycache.relative_to(ROOT).parts):
            continue
        shutil.rmtree(pycache, ignore_errors=True)
    for pattern in ("*.log", "ОТЧЁТ_*.txt"):
        for item in ROOT.glob(pattern):
            try:
                item.unlink()
            except OSError:
                pass


def _assert_required_files() -> None:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).exists()]
    if missing:
        raise SystemExit("Missing required files: " + ", ".join(missing))


def _assert_archive_hygiene() -> None:
    bad: list[str] = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        parts = set(rel.parts)
        if parts & IGNORED_DIR_NAMES:
            continue
        if any(part.startswith("test_run") or part.endswith("_run") for part in rel.parts):
            bad.append(str(rel))
            continue
        if path.is_dir() and path.name in FORBIDDEN_DIR_NAMES:
            bad.append(str(rel))
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            bad.append(str(rel))
        if path.is_file() and path.name in {".DS_Store", "Thumbs.db", "startup_error.log"}:
            bad.append(str(rel))
    if bad:
        raise SystemExit("Forbidden generated artifacts found:\n" + "\n".join(sorted(bad)))




def _assert_smoke_entrypoints_contract() -> None:
    smoke_test = (ROOT / "smoke_test.py").read_text(encoding="utf-8", errors="replace")
    smoke_combined = (ROOT / "smoke_test_combined.py").read_text(encoding="utf-8", errors="replace")
    required_smoke_test = ["from smoke_combined_runner import run", 'if __name__ == "__main__":', "run()"]
    missing = [snippet for snippet in required_smoke_test if snippet not in smoke_test]
    if missing:
        raise SystemExit("smoke_test.py is not an executable smoke entrypoint: " + ", ".join(missing))
    for snippet in ["from smoke_combined_runner import run", 'if __name__ == "__main__":', "run()"]:
        if snippet not in smoke_combined:
            raise SystemExit(f"smoke_test_combined.py misses smoke entrypoint snippet: {snippet}")

def _assert_settings_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _settings_payload_for_disk",
        "os.replace(tmp_path, self._settings_path)",
        "settings.broken.",
        "Production-контракт",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Settings persistence contract is incomplete: " + ", ".join(missing))


def _assert_build_contract() -> None:
    build = (ROOT / "build_exe_windows.bat").read_text(encoding="utf-8", errors="replace")
    workflow = (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
    for snippet in ["release_check.py", "version_info.txt", "--noupx", "MedicalDiaryAutofill.exe"]:
        if snippet not in build:
            raise SystemExit(f"build_exe_windows.bat misses production snippet: {snippet}")
    release_zip = (ROOT / "make_release_zip.py").read_text(encoding="utf-8")
    for snippet in ['".spec"', '".DS_Store"', '"Thumbs.db"', '".vscode"', '".idea"']:
        if snippet not in release_zip:
            raise SystemExit(f"make_release_zip.py misses archive hygiene snippet: {snippet}")
    for snippet in [
        "permissions:",
        "contents: read",
        "concurrency:",
        "cancel-in-progress: true",
        "timeout-minutes:",
        "release_check.py",
        "Upload source release artifact",
        "Upload EXE artifact",
    ]:
        if snippet not in workflow:
            raise SystemExit(f"GitHub Actions workflow misses production snippet: {snippet}")
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8", errors="replace")
    for snippet in ["*.py text eol=lf", "*.bat text eol=crlf", "*.docx binary", "*.zip binary"]:
        if snippet not in attrs:
            raise SystemExit(f".gitattributes misses repository hygiene snippet: {snippet}")


def _assert_ui_selected_state_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _redraw_selection_controls",
        "Выбранное состояние без чекбокса/галочки",
        "Выбранное состояние без грубой заливки и без галочки",
        "Галочки на выбранных кнопках намеренно не рисуем",
        "нажатые кнопки получают лёгкий цветовой градиент",
        "При фактическом нажатии большая кнопка получает лёгкий",
        "или нажмите здесь, чтобы выбрать файл",
        "selected=lambda: bool(self.status_files)",
        'selected=lambda: bool(self.diary_files or getattr(self, "diary_template_dir", ""))',
        "persistent selected state",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("UI selected-state contract is incomplete: " + ", ".join(missing))




def _assert_startup_state_contract() -> None:
    from app_initialization import AppInitializationMixin

    globals_map = AppInitializationMixin._init_medical_output_state.__globals__
    required_globals = ["DOCUMENT_ORDER", "DIARY_KIND"]
    missing = [name for name in required_globals if name not in globals_map]
    if missing:
        raise SystemExit("Startup app-state contract is incomplete: " + ", ".join(missing))
    if "discharge" not in tuple(globals_map["DOCUMENT_ORDER"]):
        raise SystemExit("Startup DOCUMENT_ORDER contract is invalid")

def _assert_prod_audit_contract() -> None:
    _run([sys.executable, "prod_audit.py"], timeout=120)


def _assert_dnd_contract() -> None:
    _run([sys.executable, "dnd_contract_check.py"], timeout=60)


def _assert_performance_contract() -> None:
    # Avoid a nested subprocess chain (release_check -> performance_check -> python -c),
    # which made the gate harder to diagnose when startup import probing stalled.
    # performance_check.py still remains executable standalone; here we reuse its
    # exact probe code and run one isolated child process with a bounded timeout.
    from performance_check import startup_import_probe_code

    _run([sys.executable, "-c", startup_import_probe_code()], timeout=45)


def _assert_sick_leave_popup_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _should_prompt_discharge_sick_leave_number",
        "return discharge_selected and sick_selected and number_missing",
        "Номер ЛН относится только к документу «Выписной эпикриз»",
        "Number popup must not open from the sick-leave Yes button",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source and snippet not in (ROOT / "smoke_test_combined.py").read_text(encoding="utf-8")]
    if missing:
        raise SystemExit("Sick-leave popup contract is incomplete: " + ", ".join(missing))

def _assert_layout_balance_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        'heights = {"01": 232, "02": 100, "03": 98, "04": 156}',
        'Суммарная высота 01+02 сохранена',
        'Единые боковые отступы у всех блоков',
        'files.grid_columnconfigure(0, minsize=self._px(190, 128))',
        'files.grid_columnconfigure(2, minsize=self._px(146, 104))',
        'field_height = self._px(36 if self._compact_ui else 40, 26)',
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Layout balance contract is incomplete: " + ", ".join(missing))


def _assert_discharge_date_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _ensure_discharge_date",
        "def _prompt_discharge_date",
        'title="Дата выписки"',
        "она подставляется в выписной эпикриз",
        "ДДММГГГГ, ДДММГГ или коротко ДМГГ",
        'parse_date("10052026")',
        'parse_date("1126")',
        'parse_full_date("11062026")',
        'parse_full_date("1126")',
        'primary_drop_hint_label',
        'drop.grid_propagate(False)',
        'drop_height = self._px(96 if self._compact_ui else 106, 78)',
        'self.primary_drop_hint_label.config(text="", fg=FIELD)',
        'строка статуса не меняет высоту',
        'def _on_discharge_date_field_commit',
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Discharge-date contract is incomplete: " + ", ".join(missing))



def _assert_audit_hardening_contract() -> None:
    source = _project_python_source()
    required_snippets = [
        "def _truncate_label_text",
        "single_line=self._compact_ui",
        "def _select_default_printer_sync",
        "_printer_refresh_in_progress",
        "template_path = bundled_template_path(kind)",
        "from datetime import date",
        r"\d{4,8}",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in source]
    if missing:
        raise SystemExit("Audit-hardening contract is incomplete: " + ", ".join(missing))
    diary_dates = (ROOT / "diary_table_dates.py").read_text(encoding="utf-8", errors="replace")
    if "def cell_int" in diary_dates or "def should_remove_holiday" in diary_dates:
        raise SystemExit("diary_table_dates.py reintroduced duplicated numeric helpers")

def main() -> None:
    os.chdir(ROOT)
    _remove_generated_outputs()

    _print_step("Required files")
    _assert_required_files()

    _print_step("Python compileall")
    if not compileall.compile_dir(str(ROOT), quiet=1, maxlevels=10):
        raise SystemExit("compileall failed")

    _print_step("Smoke entrypoints")
    _assert_smoke_entrypoints_contract()

    _print_step("Performance contract")
    # Run startup-import performance before smoke/prod checks. Those checks can
    # import document-heavy modules by design; the performance probe itself must
    # stay a clean isolated startup measurement.
    _assert_performance_contract()

    _print_step("Production audit")
    _assert_prod_audit_contract()

    _print_step("Drag-and-drop contract")
    _assert_dnd_contract()

    _print_step("Smoke tests")
    # smoke_test.py is the canonical executable entrypoint and delegates to the
    # same split combined suite as smoke_test_combined.py. Running both executes
    # the identical heavy DOCX regression corpus twice and made release_check
    # unnecessarily slow/fragile in constrained terminals. The entrypoint contract
    # above still verifies that smoke_test_combined.py remains executable.
    _run([sys.executable, "smoke_test.py"], timeout=180)

    _print_step("Startup state contract")
    _assert_startup_state_contract()

    _print_step("Production contracts")
    _assert_settings_contract()
    _assert_build_contract()
    _assert_ui_selected_state_contract()
    _assert_sick_leave_popup_contract()
    _assert_discharge_date_contract()
    _assert_layout_balance_contract()
    _assert_audit_hardening_contract()

    _print_step("Cleanup and archive hygiene")
    _remove_generated_outputs()
    _assert_archive_hygiene()

    print("\nRELEASE CHECK OK")


if __name__ == "__main__":
    main()
