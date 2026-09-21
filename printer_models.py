from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PrintResult:
    printed_files: list[Path]
    errors: list[str]
