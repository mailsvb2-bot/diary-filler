"""Regression coverage for the in-repository licensing server core."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import license_client as client
from licensing_server.core import (
    OWNER_CODE_SCRYPT_HEX,
    _scrypt_code,
    issue_license,
    new_order_access_token,
    order_token_hash,
    order_token_matches,
    public_key_b64,
)
from licensing_server.store import LicenseStore
from licensing_server.yookassa import YooKassaClient


def main() -> None:
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    private_b64 = base64.b64encode(private_raw).decode("ascii")
    public_b64 = public_key_b64(private_b64)
    machine = "a" * 64

    calendar_cases = [
        (datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc), datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)),
        (datetime(2028, 1, 31, 12, 0, tzinfo=timezone.utc), datetime(2028, 2, 29, 12, 0, tzinfo=timezone.utc)),
        (datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc), datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)),
        (datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc), datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)),
        (datetime(2028, 2, 29, 12, 0, tzinfo=timezone.utc), datetime(2028, 3, 29, 12, 0, tzinfo=timezone.utc)),
        (datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc), datetime(2027, 1, 31, 12, 0, tzinfo=timezone.utc)),
    ]
    for issued_at, expected_until in calendar_cases:
        calendar_license = issue_license(
            private_b64,
            machine_hash=machine,
            order_id="calendar-boundary",
            owner=False,
            now=issued_at,
        )
        assert calendar_license["schema"] == client.LICENSE_SCHEMA
        calendar_payload = calendar_license["license"]["payload"]
        assert client._parse_utc(calendar_payload["valid_until"]) == expected_until

    payment = {
        "status": "succeeded",
        "paid": True,
        "amount": {"value": "100.00", "currency": "RUB"},
        "metadata": {"order_id": "order-1", "product_id": "diary_filler"},
    }
    assert YooKassaClient.payment_matches_order(payment, order_id="order-1", amount_rub=100)
    assert not YooKassaClient.payment_matches_order(payment, order_id="order-2", amount_rub=100)
    assert not YooKassaClient.payment_matches_order(payment, order_id="order-1", amount_rub=101)

    app_source = (ROOT / "licensing_server" / "app.py").read_text(encoding="utf-8")
    assert "def reconcile_payment(row: dict)" in app_source
    assert "row = reconcile_payment(row)" in app_source
    assert "provider.get_payment" in app_source
    assert '"server_time": datetime.now(timezone.utc).isoformat()' in app_source
    assert 'order_limiter.allow(f"{client_ip(request)}|{machine}")' in app_source

    token = new_order_access_token()
    digest = order_token_hash(token)
    assert order_token_matches(token, digest)
    assert not order_token_matches(token + "x", digest)

    # Production owner code is stored only as a memory-hard digest. Lock the
    # exact verifier value without committing the plaintext owner code.
    assert OWNER_CODE_SCRYPT_HEX == "1fd2c06f2a6d893c9f8ee8a4b2253f0138623116090a4ab3ef5b0c3ee65f0281"
    assert len(OWNER_CODE_SCRYPT_HEX) == 64
    assert _scrypt_code("test-owner-code") != OWNER_CODE_SCRYPT_HEX

    with tempfile.TemporaryDirectory() as td:
        store = LicenseStore(Path(td) / "licenses.sqlite3")
        store.create_order(
            order_id="order-1",
            token_hash=digest,
            machine_hash=machine,
            amount_rub=100,
            provider_payment_id="payment-1",
            payment_url="https://pay.example/1",
        )
        row = store.get_order("order-1")
        assert row and row["status"] == "pending"
        store.mark_paid("order-1")
        assert store.get_order("order-1")["status"] == "paid"

        paid = issue_license(
            private_b64,
            machine_hash=machine,
            order_id="order-1",
            owner=False,
            now=datetime.now(timezone.utc),
        )
        store.save_license("order-1", paid)
        assert store.get_order("order-1")["status"] == "license_issued"
        assert store.load_license("order-1") == paid

        payload = paid["license"]["payload"]
        assert payload["metadata"]["product_id"] == "diary_filler"
        assert payload["plan"] == "doctor_start"
        end = client._parse_utc(payload["valid_until"])
        issued_at = client._parse_utc(payload["issued_at"])
        assert end == client._add_calendar_month(issued_at)

        os.environ["LOCALAPPDATA"] = td
        config = client.LicenseRuntimeConfig(
            server_url="https://licenses.example.com",
            public_key_b64=public_b64,
            required=True,
        )
        old_fingerprint = client.machine_fingerprint
        client.machine_fingerprint = lambda: machine
        try:
            assert client._evaluate_document(
                paid,
                config,
                allow_uninitialized_clock=True,
            ).mode == "paid"
            owner = issue_license(
                private_b64,
                machine_hash=machine,
                order_id=None,
                owner=True,
            )
            owner_status = client._evaluate_document(owner, config)
            assert owner_status.active and owner_status.owner_unlimited
        finally:
            client.machine_fingerprint = old_fingerprint

    print("LICENSE SERVER REGRESSION OK")


if __name__ == "__main__":
    main()
