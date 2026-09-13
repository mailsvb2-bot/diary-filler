"""Prove that support diagnostics stay technical and do not expose patient paths."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


def main_check() -> None:
    fake_patient = "Сверхсекретный Пациент Иванов"
    with tempfile.TemporaryDirectory(prefix="medical-autofill-privacy-") as tmp:
        private_path = Path(tmp) / fake_patient / "Первичный осмотр.docx"
        raw = (
            f'RuntimeError: failed for --intake-primary "{private_path}"\n'
            f'home={Path.home()}\\private\\thing\n'
        )
        safe = main._support_sanitize_diagnostics(raw)
        if fake_patient in safe or str(private_path) in safe:
            raise SystemExit("PRIVACY DIAGNOSTICS FAILED: patient path leaked")
        if str(Path.home()) in safe:
            raise SystemExit("PRIVACY DIAGNOSTICS FAILED: home path leaked")
        if "<REDACTED_PRIMARY>" not in safe:
            raise SystemExit("PRIVACY DIAGNOSTICS FAILED: intake path was not redacted")

    exc = RuntimeError(f"synthetic error for {fake_patient}")
    code = main._support_error_code("startup", exc)
    if not code.startswith("MDA-STARTUP-RUNTIMEERROR"):
        raise SystemExit(f"PRIVACY DIAGNOSTICS FAILED: unstable support code {code}")

    source = Path(main.__file__).read_text(encoding="utf-8", errors="replace")
    if "Код ошибки: {code}" not in source:
        raise SystemExit("PRIVACY DIAGNOSTICS FAILED: user-visible error lacks support code")
    if "{exc}" in source:
        raise SystemExit("PRIVACY DIAGNOSTICS FAILED: raw exception is shown to user")

    print("PRIVACY DIAGNOSTICS OK")


if __name__ == "__main__":
    main_check()
