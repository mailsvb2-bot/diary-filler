"""Cryptographic core for the MedicalDiaryAutofill licensing service."""
from __future__ import annotations

import base64
import calendar
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRODUCT_ID = "diary_filler"
LICENSE_SCHEMA = "dokkomplekt.license.v1"
OWNER_SCRYPT_SALT = b"diary-filler-owner-bootstrap-v1"
OWNER_SCRYPT_N = 1 << 14
OWNER_SCRYPT_R = 8
OWNER_SCRYPT_P = 1
OWNER_SCRYPT_DKLEN = 32
# Fixed to the requested owner code without storing the plaintext in source.
OWNER_CODE_SCRYPT_HEX = "1fd2c06f2a6d893c9f8ee8a4b2253f0138623116090a4ab3ef5b0c3ee65f0281"
_MACHINE_RE = re.compile(r"^[0-9a-f]{64}$")


def _add_calendar_month(value: datetime) -> datetime:
    if value.month == 12:
        year, month = value.year + 1, 1
    else:
        year, month = value.year, value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


class LicensingServerError(RuntimeError):
    pass


def canonical_payload(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def validate_machine_hash(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _MACHINE_RE.fullmatch(normalized):
        raise LicensingServerError("machine_hash must be a 64-character lowercase SHA-256 hex digest")
    return normalized


def new_order_access_token() -> str:
    return secrets.token_urlsafe(32)


def order_token_hash(token: str) -> str:
    value = str(token or "").strip()
    if len(value) < 32 or len(value) > 512:
        raise LicensingServerError("invalid order access token")
    return hashlib.sha256(b"diary-filler-order-token-v1\0" + value.encode("utf-8")).hexdigest()


def order_token_matches(token: str, expected_hash: str) -> bool:
    try:
        actual = order_token_hash(token)
    except LicensingServerError:
        return False
    return hmac.compare_digest(actual, str(expected_hash or "").strip().lower())


def _scrypt_code(code: str) -> str:
    value = str(code or "").strip()
    if not value or len(value) > 512 or any(ch in "\r\n\x00" for ch in value):
        return ""
    return hashlib.scrypt(
        value.encode("utf-8"),
        salt=OWNER_SCRYPT_SALT,
        n=OWNER_SCRYPT_N,
        r=OWNER_SCRYPT_R,
        p=OWNER_SCRYPT_P,
        dklen=OWNER_SCRYPT_DKLEN,
    ).hex()


def owner_code_matches(code: str) -> bool:
    derived = _scrypt_code(code)
    return bool(derived) and hmac.compare_digest(derived, OWNER_CODE_SCRYPT_HEX)


def load_private_key(private_key_b64: str) -> Ed25519PrivateKey:
    try:
        raw = base64.b64decode(str(private_key_b64 or "").strip(), validate=True)
    except Exception as exc:
        raise LicensingServerError("issuer private key is not valid base64") from exc
    if len(raw) != 32:
        raise LicensingServerError("issuer private key must decode to 32 raw bytes")
    try:
        return Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError as exc:
        raise LicensingServerError("issuer private key is invalid") from exc


def public_key_b64(private_key_b64: str) -> str:
    key = load_private_key(private_key_b64)
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def issue_license(
    private_key_b64: str,
    *,
    machine_hash: str,
    order_id: str | None,
    owner: bool,
    now: datetime | None = None,
) -> dict:
    machine = validate_machine_hash(machine_hash)
    issued = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    valid_from = issued - timedelta(minutes=5)
    valid_until = (
        datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        if owner
        else _add_calendar_month(issued)
    )
    metadata = {"product_id": PRODUCT_ID}
    plan = "doctor_start"
    features: list[str] = []
    document_limit = 1_000_000
    template_limit = 10_000
    profile_limit = 100
    if owner:
        plan = "vip"
        metadata.update({"role": "owner_superadmin", "access": "unlimited"})
        features = [
            "batch_generation",
            "batch_print",
            "profile_export",
            "profile_import",
            "department_profile",
            "role_management",
            "local_license_server",
            "all_features",
        ]
        document_limit = 2_000_000_000
        template_limit = 2_000_000_000
        profile_limit = 2_000_000_000

    payload = {
        "license_id": str(uuid.uuid4()),
        "order_id": None if owner else str(order_id or ""),
        "plan": plan,
        "owner_name": None,
        "organization_name": None,
        "seats": 1,
        "allowed_machines": [machine],
        "valid_from": _iso_z(valid_from),
        "valid_until": _iso_z(valid_until),
        "document_limit_month": document_limit,
        "template_limit": template_limit,
        "profile_limit": profile_limit,
        "features": features,
        "grace_days": 0,
        "watermark_mode": "none",
        "issued_by": "medical-diary-license-server",
        "issued_at": _iso_z(issued),
        "metadata": metadata,
    }
    signature = load_private_key(private_key_b64).sign(canonical_payload(payload))
    return {
        "schema": LICENSE_SCHEMA,
        "license": {
            "payload": payload,
            "signature_alg": "ed25519",
            "signature": base64.b64encode(signature).decode("ascii"),
        },
    }
