"""Run the locked source-level regression suite locally with one command.

Usage:
    python tools/run_regression_suite.py --quick
    python tools/run_regression_suite.py --full

Windows packaged-EXE and installer tests remain separate because they need a
built binary/installer; CI always runs those after this source-level contour.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

QUICK = (
    "tools/regression_lock_check.py",
    "tools/ci_gate_lock.py",
    "tools/production_safety_gate.py",
    "tools/privacy_diagnostics_check.py",
    "tests/desktop_intake_contract_check.py",
    "tests/intake_lifecycle_regression.py",
    "gui_runtime_check.py",
)

FULL_EXTRA = (
    "prod_audit.py",
    "release_check.py",
    "tools/full_patient_replay_check.py",
    "tools/staff_profile_regression.py",
    "tools/gender_generation_regression_matrix.py",
)


def _run(relative: str) -> None:
    print(f"\n=== {relative} ===", flush=True)
    subprocess.run([sys.executable, relative], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="run fast source/lifecycle locks")
    parser.add_argument("--full", action="store_true", help="run quick locks plus generation regressions")
    args = parser.parse_args()
    if args.quick and args.full:
        parser.error("choose only one of --quick or --full")
    full = args.full or not args.quick

    for script in QUICK:
        _run(script)
    if full:
        for script in FULL_EXTRA:
            _run(script)

    mode = "FULL" if full else "QUICK"
    print(f"\nREGRESSION SUITE {mode} OK")
    print("Packaged Windows E2E and installer/uninstall smoke are enforced by GitHub Actions.")


if __name__ == "__main__":
    main()
