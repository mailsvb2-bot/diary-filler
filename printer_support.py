"""Facade for Windows printer discovery and DOCX printing helpers."""
from __future__ import annotations

from printer_discovery import get_default_printer, list_printers
from printer_jobs import _print_file_default, _print_file_with_pywin32, _set_default_printer, print_files
from printer_models import PrintResult
from printer_platform import _startupinfo, is_windows

__all__ = [
    "PrintResult",
    "is_windows",
    "_startupinfo",
    "list_printers",
    "get_default_printer",
    "_set_default_printer",
    "_print_file_with_pywin32",
    "_print_file_default",
    "print_files",
]
