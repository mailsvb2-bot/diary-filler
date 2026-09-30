"""Compatibility entrypoint for the former Windows-11-only live E2E contract."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("windows_live_e2e_contract.py")), run_name="__main__")
