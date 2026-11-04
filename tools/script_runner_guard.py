"""Fail if a script executed by release_check.py or a CI workflow defines
test_* functions but would run none of them when invoked as a script.

A test file without an ``if __name__ == "__main__":`` runner is a silent no-op
under ``python tests/x.py``; an explicit runner that forgets a function silently
skips it. Standard library only.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_RE = re.compile(r"(?<![\\w./-])((?:tests|tools)/[\\w/.-]+\\.py|[\\w-]+\\.py)")


def invoked_scripts(root: Path = ROOT) -> list[Path]:
    sources = [root / "release_check.py", *sorted((root / ".github" / "workflows").glob("*.yml"))]
    found: set[Path] = set()
    for source in sources:
        if not source.is_file():
            continue
        for rel in _SCRIPT_RE.findall(source.read_text(encoding="utf-8", errors="replace")):
            path = root / rel
            if path.is_file():
                found.add(path)
    return sorted(found)


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If):
        return False
    try:
        text = ast.unparse(node.test)
    except Exception:
        return False
    return "__name__" in text and "__main__" in text


def script_problems(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return [f"{path.name}: syntax error {exc}"]
    tests = [n.name for n in tree.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    if not tests:
        return []
    guards = [n for n in tree.body if _is_main_guard(n)]
    if not guards:
        return [f"{path.name}: defines {len(tests)} test_* functions but has no __main__ runner"]
    body = "\n".join(ast.unparse(g) for g in guards)
    if "startswith('test_')" in body or 'startswith("test_")' in body or "unittest.main" in body or "pytest.main" in body:
        return []
    called = {n.func.id for g in guards for n in ast.walk(g)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    missing = [name for name in tests if name not in called]
    return [f"{path.name}: __main__ runner skips {name}" for name in missing]


def find_noop_scripts(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for script in invoked_scripts(root):
        problems.extend(script_problems(script))
    return problems


def main() -> int:
    problems = find_noop_scripts(ROOT)
    for problem in problems:
        print("TEST RUNNER GUARD:", problem)
    if problems:
        return 1
    print(f"TEST RUNNER GUARD: OK ({len(invoked_scripts(ROOT))} scripts checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
