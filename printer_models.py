from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PrintResult:
    printed_files: list[Path]
    errors: list[str]
