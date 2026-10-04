"""Fail-closed compatibility check between release client and license server."""
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

EXPECTED_PRODUCT_ID = "diary_filler"


def validate_health(payload: dict, expected_public_key_b64: str) -> None:
    if payload.get("status") != "ok":
        raise RuntimeError("license server health status is not ok")
    if payload.get("product_id") != EXPECTED_PRODUCT_ID:
        raise RuntimeError("license server product_id does not match diary_filler")
    durability = payload.get("durability")
    if not isinstance(durability, dict):
        raise RuntimeError("license server durability status is missing")
    if durability.get("status") != "ok":
        raise RuntimeError("license server durable backup is degraded")
    if durability.get("backup_configured") is not True:
        raise RuntimeError("license server backup is not configured")
    if durability.get("primary_integrity") != "ok" or durability.get("backup_integrity") != "ok":
        raise RuntimeError("license server database integrity is not healthy")
    actual = str(payload.get("public_key_b64") or "").strip()
    expected = str(expected_public_key_b64 or "").strip()
    try:
        actual_raw = base64.b64decode(actual, validate=True)
        expected_raw = base64.b64decode(expected, validate=True)
    except Exception as exc:
        raise RuntimeError("license server/client public key is not valid base64") from exc
    if len(actual_raw) != 32 or len(expected_raw) != 32:
        raise RuntimeError("license server/client Ed25519 public key must be 32 bytes")
    if actual_raw != expected_raw:
        raise RuntimeError("license server public key does not match the key embedded in the client")


def fetch_health(server_url: str) -> dict:
    url = str(server_url or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError("production license server URL must use HTTPS")
    request = urllib.request.Request(
        url + "/health",
        headers={"Accept": "application/json", "User-Agent": "MedicalDiaryAutofill-ReleasePreflight/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(64 * 1024)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"license server health returned HTTP {exc.code}") from exc
    except OSError as exc:
        raise RuntimeError("license server health is unreachable") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("license server health returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("license server health returned invalid payload")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server-url",
        default=os.environ.get("MEDICAL_AUTOFILL_LICENSE_SERVER_URL", ""),
    )
    parser.add_argument(
        "--public-key-b64",
        default=os.environ.get("MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64", ""),
    )
    args = parser.parse_args()
    if not args.server_url.strip() or not args.public_key_b64.strip():
        raise SystemExit("license server URL and public key are required")
    payload = fetch_health(args.server_url)
    validate_health(payload, args.public_key_b64)
    print("LICENSE SERVER RELEASE PREFLIGHT OK")


if __name__ == "__main__":
    main()
