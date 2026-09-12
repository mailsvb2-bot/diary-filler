"""Verify the exact PyInstaller EXE that will be handed to users."""

from __future__ import annotations

import os
import struct
import subprocess
from pathlib import Path

from app_config import APP_VERSION

ROOT = Path(__file__).resolve().parent
EXE = ROOT / "dist" / "MedicalDiaryAutofill.exe"
PROBE_RESULT = ROOT / "build" / "exe_startup_probe.txt"


def _pe_has_authenticode_signature(path: Path) -> bool:
    """Return True when the PE Security Directory points to a certificate table."""
    data = path.read_bytes()
    if len(data) < 0x100 or data[:2] != b"MZ":
        raise SystemExit(f"Not a PE executable: {path}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\\0\\0":
        raise SystemExit(f"Invalid PE signature: {path}")
    optional_offset = pe_offset + 24
    magic = struct.unpack_from("<H", data, optional_offset)[0]
    if magic == 0x20B:  # PE32+
        data_directory_offset = optional_offset + 112
    elif magic == 0x10B:  # PE32
        data_directory_offset = optional_offset + 96
    else:
        raise SystemExit(f"Unsupported PE optional-header magic: 0x{magic:04x}")
    security_entry = data_directory_offset + (8 * 4)
    cert_offset, cert_size = struct.unpack_from("<II", data, security_entry)
    return bool(cert_offset and cert_size)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("verify_built_exe.py must run on Windows")
    if not EXE.exists():
        raise SystemExit(f"Built EXE not found: {EXE}")

    PROBE_RESULT.parent.mkdir(parents=True, exist_ok=True)
    PROBE_RESULT.unlink(missing_ok=True)
    env = os.environ.copy()
    env["MEDICAL_AUTOFILL_STARTUP_PROBE"] = "1"
    env["MEDICAL_AUTOFILL_STARTUP_PROBE_RESULT"] = str(PROBE_RESULT)
    env["APPDATA"] = str(ROOT / "build" / "probe-appdata")

    completed = subprocess.run([str(EXE)], env=env, cwd=ROOT, timeout=45, check=False)
    if completed.returncode != 0:
        details = PROBE_RESULT.read_text(encoding="utf-8", errors="replace") if PROBE_RESULT.exists() else ""
        raise SystemExit(f"Packaged EXE startup probe failed with exit {completed.returncode}:\n{details}")
    if not PROBE_RESULT.exists():
        raise SystemExit("Packaged EXE exited without writing its startup-probe evidence")
    probe = PROBE_RESULT.read_text(encoding="utf-8", errors="replace")
    required = ["OK", f"version={APP_VERSION}", "dnd=1"]
    missing = [item for item in required if item not in probe]
    if missing:
        raise SystemExit("Packaged EXE startup evidence is incomplete: " + ", ".join(missing))

    signed = _pe_has_authenticode_signature(EXE)
    require_signed = os.environ.get("MEDICAL_AUTOFILL_REQUIRE_SIGNED_EXE", "").strip() == "1"
    if require_signed and not signed:
        raise SystemExit("Official release requires an Authenticode-signed EXE")
    print(f"PACKAGED EXE PROBE OK: version={APP_VERSION}, dnd=1, signed={int(signed)}")
    if not signed:
        print("WARNING: EXE is unsigned. CI artifact is valid for QA, but must not be promoted as the official signed release.")


if __name__ == "__main__":
    main()
