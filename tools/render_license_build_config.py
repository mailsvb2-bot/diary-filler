"""Generate the public licensing build configuration consumed by PyInstaller."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
from urllib.parse import urlparse


def _boolean(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/generated/license_build_config.py")
    args = parser.parse_args()

    server_url = os.environ.get("MEDICAL_AUTOFILL_LICENSE_SERVER_URL", "").strip().rstrip("/")
    public_key = os.environ.get("MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64", "").strip()
    required = _boolean(os.environ.get("MEDICAL_AUTOFILL_LICENSE_REQUIRED", "0"))
    policy_mode = os.environ.get("MEDICAL_AUTOFILL_RELEASE_LICENSE_MODE", "").strip().lower()
    if policy_mode not in {"", "unlicensed", "licensed"}:
        raise SystemExit("unsupported release licensing policy")
    if policy_mode == "unlicensed" and (required or server_url or public_key):
        raise SystemExit(
            "unlicensed release policy requires LICENSE_REQUIRED=0 and empty server/key"
        )
    if policy_mode == "licensed" and not required:
        raise SystemExit("licensed release policy requires LICENSE_REQUIRED=1")

    if required:
        if not server_url or not public_key:
            raise SystemExit("license enforcement requires server URL and Ed25519 public key")
        parsed = urlparse(server_url)
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise SystemExit("production license server URL must use HTTPS")
        try:
            key = base64.b64decode(public_key, validate=True)
        except Exception as exc:
            raise SystemExit("license public key is not valid base64") from exc
        if len(key) != 32:
            raise SystemExit("license public key must decode to 32 bytes")

    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# generated; contains public licensing configuration only\n"
        + f"LICENSE_SERVER_URL = {server_url!r}\n"
        + f"LICENSE_PUBLIC_KEY_B64 = {public_key!r}\n"
        + f"LICENSE_REQUIRED = {required!r}\n"
        + f"LICENSE_POLICY_MODE = {policy_mode!r}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
