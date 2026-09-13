"""Static fail-closed checks for the outer production-safety/support layer."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_RUNTIME_PYTHON_FILES = 125
RELEASE_ONLY_ENTRYPOINTS = {"gui_runtime_check.py", "verify_built_exe.py"}


def fail(message: str) -> None:
    raise SystemExit("PRODUCTION SAFETY GATE FAILED: " + message)


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        fail(f"missing required file: {path}")
    return target.read_text(encoding="utf-8", errors="replace")


def assert_runtime_budget() -> None:
    root_python = sorted(ROOT.glob("*.py"))
    runtime = [path for path in root_python if path.name not in RELEASE_ONLY_ENTRYPOINTS]
    if len(runtime) > MAX_RUNTIME_PYTHON_FILES:
        fail(f"runtime Python budget increased: {len(runtime)} > {MAX_RUNTIME_PYTHON_FILES}")


def assert_behavior_contracts() -> None:
    behavior = read("USER_BEHAVIOR_CONTRACT.md")
    regression = read("REGRESSION_CONTOUR.md")
    for marker in (
        "must **not replace, fork or silently alter the document-creation mechanics**",
        "_apply_primary_document_path(...)_path_placeholder",
    ):
        # The second marker is normalized below; keeping this loop explicit makes
        # accidental weakening of the contract visible in code review.
        pass
    if "must **not replace, fork or silently alter the document-creation mechanics**" not in behavior:
        fail("behavior contract lost the no-second-mechanics rule")
    if "_apply_primary_document_path(...)" not in behavior:
        fail("behavior contract lost the canonical desktop-intake handoff")
    if "document_mechanics_guard.py" not in regression:
        fail("regression contour no longer requires the mechanics guard")


def assert_intake_boundary() -> None:
    startup = read("startup.py")
    required = (
        "nothing below generates or edits medical documents",
        "app._apply_primary_document_path(str(moved_primary), prompt_for_referral=True)",
        "The medical/diary generation engine stays",
    )
    missing = [marker for marker in required if marker not in startup]
    if missing:
        fail("desktop intake boundary drifted: " + ", ".join(missing))


def assert_self_check_is_outer_only() -> None:
    source = read("main.py")
    if 'SELF_CHECK_ARGUMENT = "--self-check"' not in source:
        fail("packaged technical self-check is missing")
    tree = ast.parse(source, filename="main.py")
    self_check_functions = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_self_check")
    }
    if not self_check_functions:
        fail("self-check functions are missing")
    body = "\n".join(self_check_functions.values())
    forbidden = (
        "MedicalDocumentService",
        "extract_docx_text",
        "parse_primary_document",
        "create_selected_outputs",
        "_create_medical_documents_impl",
        "_create_diaries_impl",
    )
    leaked = [name for name in forbidden if name in body]
    if leaked:
        fail("technical self-check entered document mechanics: " + ", ".join(leaked))


def assert_ci_wiring() -> None:
    workflow = read(".github/workflows/windows-build.yml")
    build = read("build_exe_windows.bat")
    for marker in (
        "fetch-depth: 0",
        "python tools/document_mechanics_guard.py",
        "python tools/production_safety_gate.py",
        "python gui_runtime_check.py",
        "python verify_built_exe.py",
    ):
        if marker not in workflow:
            fail(f"Windows CI lost safety marker: {marker}")
    if "python tools/production_safety_gate.py" not in build:
        fail("local Windows EXE build bypasses production safety gate")


def main() -> None:
    assert_runtime_budget()
    assert_behavior_contracts()
    assert_intake_boundary()
    assert_self_check_is_outer_only()
    assert_ci_wiring()
    print("PRODUCTION SAFETY GATE OK")


if __name__ == "__main__":
    main()
