"""Standalone regression for monthly Ed25519 licensing."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import license_client as lc


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signed_document(private_key, payload: dict) -> dict:
    signature = private_key.sign(canonical(payload))
    return {
        "schema": lc.LICENSE_SCHEMA,
        "license": {
            "payload": payload,
            "signature_alg": "ed25519",
            "signature": base64.b64encode(signature).decode("ascii"),
        },
    }


def payload(machine: str, *, days: int = 31, product: str = lc.PRODUCT_ID, owner: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    metadata = {"product_id": product}
    plan = "doctor_start"
    if owner:
        plan = "vip"
        metadata.update({"role": "owner_superadmin", "access": "unlimited"})
    return {
        "license_id": "TEST-LICENSE",
        "order_id": None if owner else "00000000-0000-0000-0000-000000000001",
        "plan": plan,
        "owner_name": None,
        "organization_name": None,
        "seats": 1,
        "allowed_machines": [machine],
        "valid_from": now.isoformat().replace("+00:00", "Z"),
        "valid_until": (now + timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        "document_limit_month": 9999999 if owner else 600,
        "template_limit": 999999 if owner else 30,
        "profile_limit": 9999 if owner else 1,
        "features": [] if not owner else [
            "batch_generation", "batch_print", "profile_export", "profile_import",
            "department_profile", "role_management", "local_license_server"
        ],
        "grace_days": 0,
        "watermark_mode": "none",
        "issued_by": "test",
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "metadata": metadata,
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        os.environ["LOCALAPPDATA"] = td
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        config = lc.LicenseRuntimeConfig(
            server_url="https://licenses.example.com",
            public_key_b64=base64.b64encode(public).decode("ascii"),
            required=True,
        )
        machine = lc.machine_fingerprint()

        # Embedded production enforcement is authoritative and cannot be
        # disabled or pointed at a different trust anchor through environment.
        fake_embedded = types.SimpleNamespace(
            LICENSE_SERVER_URL="https://embedded.example.com",
            LICENSE_PUBLIC_KEY_B64=config.public_key_b64,
            LICENSE_REQUIRED=True,
        )
        old_module = sys.modules.get("license_build_config")
        sys.modules["license_build_config"] = fake_embedded
        os.environ["MEDICAL_AUTOFILL_LICENSE_SERVER_URL"] = ""
        os.environ["MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64"] = ""
        os.environ["MEDICAL_AUTOFILL_LICENSE_REQUIRED"] = "0"
        embedded = lc.runtime_config()
        assert embedded.required
        assert embedded.server_url == "https://embedded.example.com"
        assert embedded.public_key_b64 == config.public_key_b64
        if old_module is None:
            sys.modules.pop("license_build_config", None)
        else:
            sys.modules["license_build_config"] = old_module
        os.environ.pop("MEDICAL_AUTOFILL_LICENSE_SERVER_URL", None)
        os.environ.pop("MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64", None)
        os.environ.pop("MEDICAL_AUTOFILL_LICENSE_REQUIRED", None)

        # Windows identity must not depend on hostname or reinstall-local ID
        # when the stable MachineGuid is available.
        old_guid = lc._windows_machine_guid
        old_install = lc._install_id
        lc._windows_machine_guid = lambda: "stable-guid"
        lc._install_id = lambda: "install-a"
        stable_a = lc.machine_fingerprint()
        lc._install_id = lambda: "install-b"
        stable_b = lc.machine_fingerprint()
        assert stable_a == stable_b
        lc._windows_machine_guid = old_guid
        lc._install_id = old_install

        paid = signed_document(private, payload(machine))
        assert lc.save_license(paid, config).active
        assert lc.current_status(config).mode == "paid"

        # Removing or corrupting the anti-rollback state after activation must
        # fail closed rather than reset the clock guard.
        clock_backup = lc._clock_path().read_text(encoding="utf-8")
        lc._clock_path().unlink()
        assert not lc.current_status(config).active
        lc._clock_path().write_text(clock_backup, encoding="utf-8")
        lc._clock_path().write_text("{broken", encoding="utf-8")
        assert not lc.current_status(config).active
        lc._clock_path().write_text(clock_backup, encoding="utf-8")

        # A stale local payment order can always be discarded and replaced.
        lc._save_pending_order({
            "order_id": "00000000-0000-0000-0000-000000000099",
            "order_access_token": "token",
            "payment_url": "https://pay.example.com/old",
            "amount_rub": 1,
        })
        assert lc.pending_payment_details() is not None
        lc.discard_pending_order()
        assert lc.pending_payment_details() is None

        tampered = json.loads(json.dumps(paid))
        tampered["license"]["payload"]["document_limit_month"] = 999999
        try:
            lc._evaluate_document(tampered, config)
            raise AssertionError("tampered license accepted")
        except lc.LicenseError:
            pass

        wrong_product = signed_document(private, payload(machine, product="other_product"))
        try:
            lc._evaluate_document(wrong_product, config)
            raise AssertionError("cross-product license accepted")
        except lc.LicenseError:
            pass

        wrong_machine = signed_document(private, payload("0" * 64))
        try:
            lc._evaluate_document(wrong_machine, config)
            raise AssertionError("wrong-machine license accepted")
        except lc.LicenseError:
            pass

        annual = signed_document(private, payload(machine, days=365))
        try:
            lc._evaluate_document(annual, config)
            raise AssertionError("annual paid license bypassed monthly contract")
        except lc.LicenseError:
            pass

        owner = signed_document(private, payload(machine, days=3650, owner=True))
        owner_status = lc._evaluate_document(owner, config)
        assert owner_status.active and owner_status.owner_unlimited and owner_status.mode == "owner"

        required_missing = lc.LicenseRuntimeConfig("", "", True)
        assert not lc.current_status(required_missing).active
        dev_missing = lc.LicenseRuntimeConfig("", "", False)
        assert lc.current_status(dev_missing).active

        lc._record_clock(datetime.now(timezone.utc) + timedelta(days=4))
        try:
            lc._evaluate_document(paid, config)
            raise AssertionError("clock rollback was not detected")
        except lc.LicenseError:
            pass

    print("LICENSE CLIENT REGRESSION OK")


if __name__ == "__main__":
    main()
