"""Regression for official-release license server compatibility preflight."""
from __future__ import annotations

import base64
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.license_server_preflight import validate_health


def main() -> None:
    key = base64.b64encode(bytes(range(32))).decode("ascii")
    validate_health(
        {"status": "ok", "product_id": "diary_filler", "public_key_b64": key},
        key,
    )

    failures = [
        {"status": "down", "product_id": "diary_filler", "public_key_b64": key},
        {"status": "ok", "product_id": "other", "public_key_b64": key},
        {
            "status": "ok",
            "product_id": "diary_filler",
            "public_key_b64": base64.b64encode(bytes(reversed(range(32)))).decode("ascii"),
        },
    ]
    for payload in failures:
        try:
            validate_health(payload, key)
            raise AssertionError(f"invalid health payload accepted: {payload}")
        except RuntimeError:
            pass

    print("LICENSE SERVER RELEASE PREFLIGHT REGRESSION OK")


if __name__ == "__main__":
    main()
