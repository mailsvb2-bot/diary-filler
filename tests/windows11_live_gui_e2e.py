"""Compatibility entrypoint for the former Windows-11-only live GUI E2E path."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("windows_live_gui_e2e.py")), run_name="__main__")
