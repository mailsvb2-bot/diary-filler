"""Runner for the split combined smoke regression suite."""

from __future__ import annotations

from pathlib import Path

PARTS = (
    "smoke_combined_part01_setup_contracts.py",
    "smoke_combined_part02_ui_parser_regressions.py",
    "smoke_combined_part03_medical_parser_manual.py",
    "smoke_combined_part04_medical_generation.py",
    "smoke_combined_part05_diary_basic_templates.py",
    "smoke_combined_part06_diary_columns_settings.py",
)


def run() -> None:
    root = Path(__file__).resolve().parent
    namespace = {"__name__": "__smoke_combined__", "__file__": str(root / "smoke_test_combined.py")}
    for part_name in PARTS:
        part_path = root / part_name
        code = compile(part_path.read_text(encoding="utf-8"), str(part_path), "exec")
        exec(code, namespace, namespace)
