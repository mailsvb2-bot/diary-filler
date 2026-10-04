"""Ed25519 monthly-license client for MedicalDiaryAutofill.

No patient data is read or transmitted by this module. The client sends only a
machine fingerprint and order/license metadata to the license server.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import base64
import calendar
import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import urllib.error
import urllib.parse
import urllib.request
import uuid

PRODUCT_ID = "diary_filler"
DEFAULT_PLAN = "doctor_start"
LEGACY_LICENSE_SCHEMA = "dokkomplekt.license.v1"
LICENSE_SCHEMA = "dokkomplekt.license.v2"
SUPPORTED_LICENSE_SCHEMAS = {LEGACY_LICENSE_SCHEMA, LICENSE_SCHEMA}
CLOCK_ROLLBACK_TOLERANCE = timedelta(minutes=15)


def _add_calendar_month(value: datetime) -> datetime:
    if value.month == 12:
        year, month = value.year + 1, 1
    else:
        year, month = value.year, value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


class LicenseError(RuntimeError):
    pass


class OwnerReactivationRequired(LicenseError):
    pass


class PaymentPendingError(LicenseError):
    pass


class PaymentTerminalError(LicenseError):
    pass


class LicenseExpiredError(LicenseError):
    pass


class PaidLicenseRecoveryError(LicenseError):
    pass


@dataclass(frozen=True)
class LicenseRuntimeConfig:
    server_url: str
    public_key_b64: str
    required: bool
    product_id: str = PRODUCT_ID
    default_plan: str = DEFAULT_PLAN


@dataclass(frozen=True)
class LicenseStatus:
    active: bool
    mode: str
    message: str
    plan: str = ""
    valid_until: datetime | None = None
    owner_unlimited: bool = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def runtime_config() -> LicenseRuntimeConfig:
    embedded_url = ""
    embedded_key = ""
    embedded_required = False
    try:
        import license_build_config as embedded  # type: ignore

        embedded_url = str(getattr(embedded, "LICENSE_SERVER_URL", "") or "")
        embedded_key = str(getattr(embedded, "LICENSE_PUBLIC_KEY_B64", "") or "")
        embedded_required = bool(getattr(embedded, "LICENSE_REQUIRED", False))
    except Exception:
        pass

    if embedded_required:
        # A packaged production build must not let a local process environment
        # disable enforcement or replace the compiled trust anchor/server.
        server_url = embedded_url.strip().rstrip("/")
        public_key_b64 = embedded_key.strip()
        required = True
    else:
        server_url = os.environ.get("MEDICAL_AUTOFILL_LICENSE_SERVER_URL", embedded_url).strip().rstrip("/")
        public_key_b64 = os.environ.get("MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64", embedded_key).strip()
        required = _env_bool("MEDICAL_AUTOFILL_LICENSE_REQUIRED", embedded_required)
    return LicenseRuntimeConfig(
        server_url=server_url,
        public_key_b64=public_key_b64,
        required=required,
    )


def _runtime_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA", "").strip() or os.environ.get("APPDATA", "").strip()
    return (Path(base) if base else Path.home() / ".medical_diary_autofill") / "MedicalDiaryAutofill"


def license_path() -> Path:
    return _runtime_dir() / "license.json"


def _license_backup_path() -> Path:
    base = os.environ.get("APPDATA", "").strip()
    root = Path(base) if base else _runtime_dir().parent
    return root / "MedicalDiaryAutofill" / "license-backup.json"


def _pending_order_path() -> Path:
    return _runtime_dir() / "license-order.json"


def _pending_order_backup_path() -> Path:
    base = os.environ.get("APPDATA", "").strip()
    root = Path(base) if base else _runtime_dir().parent
    return root / "MedicalDiaryAutofill" / "pending-payment-recovery.json"


def _active_order_path() -> Path:
    return _runtime_dir() / "license-active-order.json"


def _active_order_backup_path() -> Path:
    base = os.environ.get("APPDATA", "").strip()
    root = Path(base) if base else _runtime_dir().parent
    return root / "MedicalDiaryAutofill" / "paid-entitlement-recovery.json"


def _clock_path() -> Path:
    return _runtime_dir() / "license-clock.json"


def _clock_backup_path() -> Path:
    base = os.environ.get("APPDATA", "").strip()
    root = Path(base) if base else _runtime_dir().parent
    return root / "MedicalDiaryAutofill" / "license-clock-backup.json"


def _owner_marker_path() -> Path:
    base = os.environ.get("APPDATA", "").strip()
    root = Path(base) if base else _runtime_dir().parent
    return root / "MedicalDiaryAutofill" / "owner-entitlement.marker"


def _install_id_path() -> Path:
    return _runtime_dir() / "license-install-id.txt"


def _machine_fingerprint_cache_path() -> Path:
    return _runtime_dir() / "license-machine-fingerprint.json"


def _machine_fingerprint_backup_path() -> Path:
    base = os.environ.get("APPDATA", "").strip()
    root = Path(base) if base else _runtime_dir().parent
    return root / "MedicalDiaryAutofill" / "license-machine-fingerprint-backup.json"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _install_id() -> str:
    path = _install_id_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    value = uuid.uuid4().hex
    _atomic_write_text(path, value + "\n")
    return value


def _windows_machine_guid() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        access = winreg.KEY_READ
        if hasattr(winreg, "KEY_WOW64_64KEY"):
            access |= winreg.KEY_WOW64_64KEY
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            access,
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "MachineGuid")
            return str(value or "").strip()
    except Exception:
        return ""


def _valid_machine_fingerprint(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _derived_machine_fingerprint_candidates() -> tuple[set[str], bool]:
    """Return fingerprints independently derivable on this machine.

    The boolean reports whether Windows MachineGuid was available. The fallback
    install identity is included for compatibility with legitimate legacy
    activations that happened while MachineGuid was temporarily unreadable.
    """
    candidates: set[str] = set()
    machine_guid = _windows_machine_guid().strip().lower()
    if machine_guid:
        candidates.add(
            hashlib.sha256(
                f"windows-machine-guid-v1|{machine_guid}".encode("utf-8")
            ).hexdigest()
        )
    fallback_identity = (
        "portable-install-v1|"
        + platform.system().strip().lower()
        + "|"
        + _install_id().strip().lower()
    )
    candidates.add(hashlib.sha256(fallback_identity.encode("utf-8")).hexdigest())
    return candidates, bool(machine_guid)


def _decode_protected_machine_fingerprint_cache(raw: str) -> str:
    try:
        payload = json.loads(raw)
        if payload.get("schema") != 2:
            return ""
        clear = _unprotect_local_blob(
            str(payload.get("protected") or ""),
            "MedicalDiaryAutofill machine fingerprint",
        )
        protected_payload = json.loads(clear.decode("utf-8"))
        value = str(protected_payload.get("fingerprint") or "").strip().lower()
        if _valid_machine_fingerprint(value):
            return value
    except Exception:
        pass
    return ""


def _decode_legacy_primary_machine_fingerprint(raw: str) -> tuple[str, bool]:
    """Validate an old unprotected cache against current machine evidence.

    Returns (value, identity_complete). A legacy value is never accepted merely
    because it is well-formed; otherwise a copied license plus copied cache could
    bypass machine binding. Roaming backup files never accept schema 1.
    """
    try:
        payload = json.loads(raw)
        if payload.get("schema") != 1:
            return "", True
        value = str(payload.get("fingerprint") or "").strip().lower()
        if not _valid_machine_fingerprint(value):
            return "", True
        candidates, machine_guid_available = _derived_machine_fingerprint_candidates()
        if value in candidates:
            return value, True
        return "", machine_guid_available
    except Exception:
        return "", True


def _read_cached_machine_fingerprint() -> str:
    primary = _machine_fingerprint_cache_path()
    backup = _machine_fingerprint_backup_path()

    # Protected schema-2 caches are trusted through DPAPI/HMAC integrity.
    for path in (primary, backup):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        value = _decode_protected_machine_fingerprint_cache(raw)
        if not value:
            continue
        _cache_machine_fingerprint(value)
        return value

    # Legacy schema-1 migration is allowed only from the local primary cache and
    # only when its fingerprint can be independently derived on this machine.
    try:
        legacy_raw = primary.read_text(encoding="utf-8")
    except OSError:
        legacy_raw = ""
    if legacy_raw:
        value, identity_complete = _decode_legacy_primary_machine_fingerprint(legacy_raw)
        if value:
            _cache_machine_fingerprint(value)
            return value
        try:
            legacy_payload = json.loads(legacy_raw)
            legacy_value = str(legacy_payload.get("fingerprint") or "").strip().lower()
            is_legacy = legacy_payload.get("schema") == 1 and _valid_machine_fingerprint(legacy_value)
        except Exception:
            is_legacy = False
        if is_legacy and not identity_complete:
            # Do not overwrite a potentially legitimate legacy identity while
            # MachineGuid is transiently unavailable. Access stays closed, but
            # the caller can suppress duplicate-payment UX and retry later.
            raise MachineIdentityUnavailableError(
                "Не удалось надёжно подтвердить этот компьютер. Повторите проверку лицензии."
            )
    return ""


def _cache_machine_fingerprint(value: str) -> None:
    clear = json.dumps(
        {"fingerprint": value},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        protected = _protect_local_blob(clear, "MedicalDiaryAutofill machine fingerprint")
    except LicenseError:
        # Fingerprint persistence is resilience, not an activation prerequisite.
        # A transient DPAPI failure must not turn the current computer into an
        # unusable one while a valid MachineGuid/fallback identity is available.
        return
    encoded = json.dumps(
        {"schema": 2, "protected": protected},
        sort_keys=True,
    ) + "\n"
    try:
        _atomic_write_text(_machine_fingerprint_cache_path(), encoded)
    except OSError:
        pass
    try:
        _atomic_write_text(_machine_fingerprint_backup_path(), encoded)
    except OSError:
        pass


def machine_fingerprint() -> str:
    # Once an installation/user profile has chosen an identity, keep it stable.
    # This prevents a transient MachineGuid read failure on first payment from
    # turning into a different "computer" on the next launch.
    cached = _read_cached_machine_fingerprint()
    if cached:
        return cached

    machine_guid = _windows_machine_guid().strip().lower()
    if machine_guid:
        identity = f"windows-machine-guid-v1|{machine_guid}"
    else:
        identity = (
            "portable-install-v1|"
            + platform.system().strip().lower()
            + "|"
            + _install_id().strip().lower()
        )
    fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    _cache_machine_fingerprint(fingerprint)
    return fingerprint


def _parse_utc(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(raw)
    except (TypeError, ValueError) as exc:
        raise LicenseError("license timestamp is invalid") from exc
    if result.tzinfo is None:
        raise LicenseError("license timestamp has no timezone")
    return result.astimezone(timezone.utc)


def _canonical_payload(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _verify_signature(document: dict, public_key_b64: str) -> dict:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:
        raise LicenseError("Ed25519 verifier is unavailable") from exc

    schema = str(document.get("schema") or "")
    if schema not in SUPPORTED_LICENSE_SCHEMAS:
        raise LicenseError("unsupported license schema")
    signed = document.get("license")
    if not isinstance(signed, dict) or signed.get("signature_alg") != "ed25519":
        raise LicenseError("unsupported license signature")
    payload = signed.get("payload")
    if not isinstance(payload, dict):
        raise LicenseError("license payload is missing")
    try:
        key_bytes = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(str(signed.get("signature") or ""), validate=True)
    except Exception as exc:
        raise LicenseError("invalid license proof encoding") from exc
    if len(key_bytes) != 32 or len(signature) != 64:
        raise LicenseError("invalid Ed25519 key or signature length")
    try:
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(signature, _canonical_payload(payload))
    except (InvalidSignature, ValueError) as exc:
        raise LicenseError("license signature verification failed") from exc
    return payload


def _fallback_integrity_key(purpose: str) -> bytes:
    material = (
        "medical-autofill-local-integrity-v1|"
        + purpose
        + "|"
        + _windows_machine_guid().strip().lower()
        + "|"
        + _install_id().strip().lower()
    )
    return hashlib.sha256(material.encode("utf-8")).digest()


def _protect_local_blob(raw: bytes, purpose: str) -> str:
    if os.name == "nt":
        try:
            import win32crypt

            protected = win32crypt.CryptProtectData(raw, purpose, None, None, None, 0)
            return "dpapi:" + base64.b64encode(protected).decode("ascii")
        except Exception as exc:
            raise LicenseError("Windows could not protect local license state") from exc
    key = _fallback_integrity_key(purpose)
    mac = hmac.new(key, raw, hashlib.sha256).digest()
    return "hmac:" + base64.b64encode(mac + raw).decode("ascii")


def _unprotect_local_blob(value: str, purpose: str) -> bytes:
    scheme, _, encoded = str(value or "").partition(":")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise LicenseError("protected local license state is damaged") from exc
    if scheme == "dpapi":
        if os.name != "nt":
            raise LicenseError("DPAPI state is unavailable on this platform")
        try:
            import win32crypt

            _description, clear = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
            return clear
        except Exception as exc:
            raise LicenseError("Windows could not unlock local license state") from exc
    if scheme == "hmac":
        if len(raw) < 32:
            raise LicenseError("protected local license state is damaged")
        mac, clear = raw[:32], raw[32:]
        expected = hmac.new(_fallback_integrity_key(purpose), clear, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise LicenseError("protected local license state failed integrity check")
        return clear
    raise LicenseError("unsupported protected local license state")


def _write_owner_marker() -> None:
    clear = json.dumps(
        {"schema": 1, "owner": True},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    protected = _protect_local_blob(clear, "MedicalDiaryAutofill owner marker")
    _atomic_write_text(
        _owner_marker_path(),
        json.dumps({"schema": 1, "protected": protected}, ensure_ascii=False) + "\n",
    )


def _has_owner_marker() -> bool:
    try:
        outer = json.loads(_owner_marker_path().read_text(encoding="utf-8"))
        if outer.get("schema") != 1:
            return False
        clear = _unprotect_local_blob(
            str(outer.get("protected") or ""),
            "MedicalDiaryAutofill owner marker",
        )
        payload = json.loads(clear.decode("utf-8"))
        return payload == {"owner": True, "schema": 1}
    except Exception:
        return False


def _owner_reactivation_status(message: str) -> LicenseStatus:
    return LicenseStatus(
        False,
        "owner_reactivation",
        message,
        "vip",
        None,
        True,
    )


def _decode_clock_state(raw: str) -> datetime:
    try:
        outer = json.loads(raw)
        if outer.get("schema") != 2:
            raise ValueError("unsupported clock schema")
        clear = _unprotect_local_blob(
            str(outer.get("protected") or ""),
            "MedicalDiaryAutofill license clock",
        )
        payload = json.loads(clear.decode("utf-8"))
        return _parse_utc(str(payload.get("last_seen_utc") or ""))
    except LicenseError:
        raise
    except Exception as exc:
        raise LicenseError("license clock state is damaged") from exc


def _read_clock_state() -> datetime | None:
    errors: list[Exception] = []
    found = False
    primary = _clock_path()
    for path in (primary, _clock_backup_path()):
        try:
            raw = path.read_text(encoding="utf-8")
            found = True
        except FileNotFoundError:
            continue
        except OSError as exc:
            found = True
            errors.append(exc)
            continue
        try:
            value = _decode_clock_state(raw)
        except LicenseError as exc:
            errors.append(exc)
            continue
        if path != primary:
            try:
                _atomic_write_text(primary, raw)
            except OSError:
                pass
        return value
    if not found:
        return None
    raise LicenseError("license clock state is unreadable or damaged") from (
        errors[-1] if errors else None
    )


def _record_clock(now: datetime) -> None:
    previous = _read_clock_state()
    if previous is not None and previous > now:
        now = previous
    clear = json.dumps(
        {"last_seen_utc": now.isoformat()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    protected = _protect_local_blob(clear, "MedicalDiaryAutofill license clock")
    encoded = json.dumps(
        {"schema": 2, "protected": protected},
        ensure_ascii=False,
    ) + "\n"
    _atomic_write_text(_clock_path(), encoded)
    try:
        _atomic_write_text(_clock_backup_path(), encoded)
    except OSError:
        # The LocalAppData copy remains authoritative; the roaming copy is
        # resilience against accidental cleanup/corruption.
        pass


def _validate_clock(now: datetime, *, require_initialized: bool) -> None:
    previous = _read_clock_state()
    if previous is None:
        if require_initialized:
            raise LicenseError("license clock state is missing")
        return
    if previous - now > CLOCK_ROLLBACK_TOLERANCE:
        raise LicenseError("system clock rollback detected")


def _validate_config(config: LicenseRuntimeConfig) -> None:
    if not config.server_url or not config.public_key_b64:
        raise LicenseError("license server is not configured")
    parsed = urllib.parse.urlparse(config.server_url)
    loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    if parsed.scheme != "https" and not loopback:
        raise LicenseError("license server must use HTTPS")
    try:
        key = base64.b64decode(config.public_key_b64, validate=True)
    except Exception as exc:
        raise LicenseError("license public key is invalid") from exc
    if len(key) != 32:
        raise LicenseError("license public key must be 32 bytes")


def _validate_paid_calendar_period(schema: str, payload: dict, valid_until: datetime) -> None:
    issued_at = _parse_utc(str(payload.get("issued_at") or ""))
    if schema == LEGACY_LICENSE_SCHEMA:
        if valid_until - issued_at != timedelta(days=31):
            raise LicenseError("legacy paid diary-filler license has an invalid duration")
        return
    expected_until = _add_calendar_month(issued_at)
    if valid_until != expected_until:
        raise LicenseError("paid diary-filler license is not exactly one calendar month")


def _evaluate_document(
    document: dict,
    config: LicenseRuntimeConfig,
    *,
    now: datetime | None = None,
    allow_uninitialized_clock: bool = False,
) -> LicenseStatus:
    _validate_config(config)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = _verify_signature(document, config.public_key_b64)
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("product_id") != config.product_id:
        raise LicenseError("license belongs to another product")

    plan = str(payload.get("plan") or "")
    owner = (
        plan == "vip"
        and payload.get("order_id") is None
        and metadata.get("role") == "owner_superadmin"
        and metadata.get("access") == "unlimited"
    )
    allowed = payload.get("allowed_machines")
    machine_allowed = isinstance(allowed, list) and machine_fingerprint() in {str(item) for item in allowed}

    if owner:
        if not machine_allowed:
            raise OwnerReactivationRequired(
                "Требуется повторная активация лицензии на этом компьютере"
            )
        # An Ed25519-signed owner entitlement is intentionally non-expiring.
        # It must not depend on mutable anti-rollback clock state, otherwise a
        # damaged clock file could incorrectly route the owner into paid UX.
        try:
            valid_until = _parse_utc(str(payload.get("valid_until") or ""))
        except LicenseError:
            valid_until = None
        return LicenseStatus(
            True,
            "owner",
            "Лицензия активна",
            plan,
            valid_until,
            True,
        )

    if not allow_uninitialized_clock:
        _validate_clock(now, require_initialized=True)
    valid_from = _parse_utc(str(payload.get("valid_from") or ""))
    valid_until = _parse_utc(str(payload.get("valid_until") or ""))
    if now < valid_from:
        raise LicenseError("license is not valid yet")
    if now > valid_until:
        return LicenseStatus(False, "expired", "Срок лицензии истёк", plan, valid_until)
    if not machine_allowed:
        raise LicenseError("license is not valid for this computer")

    _validate_paid_calendar_period(str(document.get("schema") or ""), payload, valid_until)
    if allow_uninitialized_clock:
        for path in (_clock_path(), _clock_backup_path()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    _record_clock(now)
    return LicenseStatus(
        True,
        "paid",
        "Лицензия активна",
        plan,
        valid_until,
        False,
    )


def _locally_trusted_paid_document(
    document: dict,
    config: LicenseRuntimeConfig,
) -> bool:
    try:
        payload = _verify_signature(document, config.public_key_b64)
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("product_id") != config.product_id:
            return False
        plan = str(payload.get("plan") or "")
        owner = (
            plan == "vip"
            and payload.get("order_id") is None
            and metadata.get("role") == "owner_superadmin"
            and metadata.get("access") == "unlimited"
        )
        if owner:
            return False
        allowed = payload.get("allowed_machines")
        if not isinstance(allowed, list) or machine_fingerprint() not in {str(item) for item in allowed}:
            return False
        valid_until = _parse_utc(str(payload.get("valid_until") or ""))
        _validate_paid_calendar_period(str(document.get("schema") or ""), payload, valid_until)
        return True
    except LicenseError:
        return False


def _trusted_server_time(config: LicenseRuntimeConfig) -> datetime:
    payload = _json_request(config, "GET", "/health")
    if str(payload.get("status") or "") != "ok":
        raise LicenseError("license server health status is not ok")
    if str(payload.get("product_id") or "") != config.product_id:
        raise LicenseError("license server product_id mismatch")
    actual_key = str(payload.get("public_key_b64") or "").strip()
    try:
        actual_raw = base64.b64decode(actual_key, validate=True)
        expected_raw = base64.b64decode(config.public_key_b64.strip(), validate=True)
    except Exception as exc:
        raise LicenseError("license server public key is invalid") from exc
    if len(actual_raw) != 32 or len(expected_raw) != 32 or not hmac.compare_digest(actual_raw, expected_raw):
        raise LicenseError("license server public key mismatch")
    return _parse_utc(str(payload.get("server_time") or ""))


def _repair_paid_clock_from_server(
    document: dict,
    config: LicenseRuntimeConfig,
) -> LicenseStatus:
    payload = _verify_signature(document, config.public_key_b64)
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("product_id") != config.product_id:
        raise LicenseError("license belongs to another product")
    plan = str(payload.get("plan") or "")
    owner = (
        plan == "vip"
        and payload.get("order_id") is None
        and metadata.get("role") == "owner_superadmin"
        and metadata.get("access") == "unlimited"
    )
    if owner:
        raise LicenseError("owner entitlements do not use paid clock recovery")
    trusted_now = _trusted_server_time(config)
    return _evaluate_document(
        document,
        config,
        now=trusted_now,
        allow_uninitialized_clock=True,
    )


def _load_backup_license_document() -> dict:
    try:
        raw = _license_backup_path().read_text(encoding="utf-8")
        document = json.loads(raw)
    except Exception as exc:
        raise LicenseError("Резервная копия лицензии повреждена") from exc
    if not isinstance(document, dict):
        raise LicenseError("Резервная копия лицензии повреждена")
    return document


def _heal_primary_license_from_backup(document: dict) -> None:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    try:
        _atomic_write_text(license_path(), encoded)
    except OSError:
        pass


def _write_license_document(document: dict) -> None:
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    _atomic_write_text(license_path(), encoded)
    try:
        _atomic_write_text(_license_backup_path(), encoded)
    except OSError:
        # Primary LocalAppData copy remains authoritative. The signed roaming
        # copy is only resilience against accidental local cleanup/corruption.
        pass


def _load_license_document() -> dict:
    primary = license_path()
    errors: list[Exception] = []
    found = False
    for path in (primary, _license_backup_path()):
        try:
            raw = path.read_text(encoding="utf-8")
            found = True
        except FileNotFoundError:
            continue
        except OSError as exc:
            found = True
            errors.append(exc)
            continue
        try:
            document = json.loads(raw)
            if not isinstance(document, dict):
                raise ValueError("license document is not an object")
        except Exception as exc:
            errors.append(exc)
            continue
        if path != primary:
            try:
                _atomic_write_text(primary, raw if raw.endswith("\n") else raw + "\n")
            except OSError:
                pass
        return document
    if not found:
        raise FileNotFoundError(str(primary))
    raise LicenseError("Файл лицензии повреждён") from (errors[-1] if errors else None)


def current_status(config: LicenseRuntimeConfig | None = None) -> LicenseStatus:
    config = config or runtime_config()
    configured = bool(config.server_url and config.public_key_b64)
    if not configured:
        if config.required:
            return LicenseStatus(False, "misconfigured", "Лицензирование не настроено в сборке")
        return LicenseStatus(True, "development", "Лицензирование пока не включено в этой сборке")
    owner_marker = _has_owner_marker()
    try:
        document = _load_license_document()
    except FileNotFoundError:
        if owner_marker:
            return _owner_reactivation_status(
                "Требуется повторная активация лицензии"
            )
        if _has_active_order_credentials():
            return _paid_recovery_status(
                "Требуется восстановить уже оплаченную лицензию"
            )
        return LicenseStatus(False, "missing", "Лицензия не активирована")
    except LicenseError:
        if owner_marker:
            return _owner_reactivation_status(
                "Требуется повторная активация лицензии"
            )
        if _has_active_order_credentials():
            return _paid_recovery_status(
                "Требуется восстановить уже оплаченную лицензию"
            )
        return LicenseStatus(False, "invalid", "Файл лицензии повреждён")
    try:
        status = _evaluate_document(document, config)
        if not status.active and status.mode == "expired":
            if _locally_trusted_paid_document(document, config):
                try:
                    # Never trust a possibly-wrong workstation clock to decide
                    # that another payment is due. Confirm expiry against the
                    # configured HTTPS license server first.
                    return _repair_paid_clock_from_server(document, config)
                except LicenseError:
                    return _paid_recovery_status(
                        "Не удалось подтвердить срок уже оплаченной лицензии. Новый платёж не нужен."
                    )
            if _has_active_order_credentials():
                return _paid_recovery_status(
                    "Требуется проверить срок уже оплаченной лицензии"
                )
        return status
    except OwnerReactivationRequired as exc:
        return _owner_reactivation_status(str(exc))
    except MachineIdentityUnavailableError as exc:
        # Never turn a transient identity-read failure into a fresh invoice.
        try:
            payload = _verify_signature(document, config.public_key_b64)
            metadata = payload.get("metadata")
            plan = str(payload.get("plan") or "")
            owner = (
                isinstance(metadata, dict)
                and metadata.get("product_id") == config.product_id
                and plan == "vip"
                and payload.get("order_id") is None
                and metadata.get("role") == "owner_superadmin"
                and metadata.get("access") == "unlimited"
            )
        except LicenseError:
            owner = False
        if owner or owner_marker:
            return _owner_reactivation_status(str(exc))
        return _paid_recovery_status(
            "Не удалось надёжно подтвердить этот компьютер для уже оплаченной лицензии. Новый платёж не нужен."
        )
    except LicenseError as exc:
        # A syntactically valid primary file may still be truncated/tampered at
        # the signed payload level. Try the independent signed backup before
        # deciding that a legitimately paid entitlement is invalid.
        try:
            backup_document = _load_backup_license_document()
        except LicenseError:
            backup_document = None
        if isinstance(backup_document, dict) and backup_document != document:
            try:
                backup_status = _evaluate_document(backup_document, config)
            except OwnerReactivationRequired as backup_exc:
                _heal_primary_license_from_backup(backup_document)
                return _owner_reactivation_status(str(backup_exc))
            except LicenseError:
                if _locally_trusted_paid_document(backup_document, config):
                    try:
                        backup_status = _repair_paid_clock_from_server(
                            backup_document,
                            config,
                        )
                    except LicenseError:
                        return _paid_recovery_status(
                            "Резервная копия подтверждает уже оплаченную лицензию. Новый платёж не нужен."
                        )
                    if backup_status.active:
                        _heal_primary_license_from_backup(backup_document)
                        return backup_status
            else:
                _heal_primary_license_from_backup(backup_document)
                return backup_status
        if owner_marker:
            return _owner_reactivation_status(
                "Требуется повторная активация лицензии"
            )
        # If the signed paid license is otherwise intact but the local
        # anti-rollback clock state disappeared/corrupted, do not force a
        # second payment. Rebuild that local state from trusted HTTPS server
        # time after re-verifying signature/product/machine/period.
        if _locally_trusted_paid_document(document, config):
            try:
                repaired = _repair_paid_clock_from_server(document, config)
                if repaired.active:
                    return repaired
            except LicenseError:
                # A cryptographically valid paid entitlement must never fall
                # through to a fresh invoice just because clock recovery or
                # the network is temporarily unavailable.
                return _paid_recovery_status(
                    "Уже оплаченная лицензия требует повторной проверки. Новый платёж не нужен."
                )
        if _has_active_order_credentials():
            return _paid_recovery_status(
                "Требуется проверить уже оплаченную лицензию"
            )
        return LicenseStatus(False, "invalid", str(exc))


def save_license(
    document: dict,
    config: LicenseRuntimeConfig | None = None,
    *,
    trusted_now: datetime | None = None,
) -> LicenseStatus:
    config = config or runtime_config()
    # This entry point is used only for a freshly server-returned signed
    # entitlement. It may rebuild damaged local anti-rollback state, but all
    # signature/product/machine/period checks still run before the file is saved.
    status = _evaluate_document(
        document,
        config,
        now=trusted_now,
        allow_uninitialized_clock=True,
    )
    if not status.active:
        if status.mode == "expired":
            raise LicenseExpiredError(status.message)
        raise LicenseError(status.message)
    _write_license_document(document)
    if status.owner_unlimited:
        _write_owner_marker()
    return status


def _protect_order_token(token: str) -> str:
    return _protect_local_blob(
        token.encode("utf-8"),
        "MedicalDiaryAutofill license order",
    )


def _unprotect_order_token(value: str) -> str:
    try:
        return _unprotect_local_blob(
            value,
            "MedicalDiaryAutofill license order",
        ).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LicenseError("saved order token is damaged") from exc


def _store_order_credentials(path: Path, payload: dict, *, include_payment: bool) -> None:
    token = str(payload.get("order_access_token") or "").strip()
    order_id = str(payload.get("order_id") or "").strip()
    if not token or not order_id:
        raise LicenseError("license server returned an incomplete order")
    stored = {
        "schema": 1,
        "order_id": order_id,
        "order_access_token": _protect_order_token(token),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    if include_payment:
        stored["payment_url"] = str(payload.get("payment_url") or "")
        stored["amount_rub"] = int(payload.get("amount_rub") or 0)
    _atomic_write_text(path, json.dumps(stored, ensure_ascii=False, indent=2) + "\n")


def _load_order_credentials(path: Path, missing_message: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise LicenseError(missing_message) from exc
    if payload.get("schema") != 1:
        raise LicenseError("Сохранённые данные лицензии имеют неизвестный формат")
    payload["order_access_token"] = _unprotect_order_token(str(payload.get("order_access_token") or ""))
    return payload


def _pending_order_paths() -> tuple[Path, Path]:
    return (_pending_order_path(), _pending_order_backup_path())


def _save_pending_order(payload: dict) -> None:
    _store_order_credentials(_pending_order_path(), payload, include_payment=True)
    try:
        _store_order_credentials(
            _pending_order_backup_path(),
            payload,
            include_payment=True,
        )
    except (LicenseError, OSError):
        # Primary LocalAppData state is enough to continue; the roaming copy is
        # a second chance if local state is later lost/corrupted before license claim.
        pass


def _load_pending_order() -> dict:
    errors = []
    found = False
    for path in _pending_order_paths():
        try:
            if path.is_file():
                found = True
        except OSError:
            found = True
        try:
            order = _load_order_credentials(
                path,
                "Нет сохранённого заказа на оплату",
            )
            if path != _pending_order_path():
                try:
                    _store_order_credentials(
                        _pending_order_path(),
                        order,
                        include_payment=True,
                    )
                except (LicenseError, OSError):
                    pass
            return order
        except LicenseError as exc:
            errors.append(exc)
    if not found:
        raise LicenseError("Нет сохранённого заказа на оплату")
    raise LicenseError(
        "Сохранённые данные уже созданного счёта повреждены. Новый платёж не создан."
    ) from (errors[-1] if errors else None)


def _clear_pending_order_best_effort() -> None:
    for path in _pending_order_paths():
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _save_active_order(order: dict) -> None:
    _store_order_credentials(_active_order_path(), order, include_payment=False)
    try:
        _store_order_credentials(
            _active_order_backup_path(),
            order,
            include_payment=False,
        )
    except (LicenseError, OSError):
        # The LocalAppData copy is authoritative for the current installation;
        # the roaming copy is resilience against ordinary app reinstall/cleanup.
        pass


def _load_active_order() -> dict:
    errors = []
    for path in (_active_order_path(), _active_order_backup_path()):
        try:
            return _load_order_credentials(
                path,
                "Нет данных для восстановления оплаченной лицензии",
            )
        except LicenseError as exc:
            errors.append(exc)
    raise LicenseError("Нет читаемых данных для восстановления оплаченной лицензии") from (
        errors[-1] if errors else None
    )


def _has_active_order_credentials() -> bool:
    # Existence is enough to suppress a new charge. If DPAPI/JSON is damaged,
    # recovery will fail safely and tell the user to retry/support rather than
    # silently treating an already-paid order as nonexistent.
    for path in (_active_order_path(), _active_order_backup_path()):
        try:
            if path.is_file():
                return True
        except OSError:
            pass
    return False


def _paid_recovery_status(message: str) -> LicenseStatus:
    return LicenseStatus(
        False,
        "paid_recovery",
        message,
        "doctor_start",
        None,
        False,
    )


def _discard_active_order_if_matches(order_id: str) -> None:
    try:
        active = _load_active_order()
    except LicenseError:
        return
    if str(active.get("order_id") or "") != str(order_id):
        return
    for path in (_active_order_path(), _active_order_backup_path()):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _json_request(
    config: LicenseRuntimeConfig,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    bearer: str = "",
) -> dict:
    _validate_config(config)
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "MedicalDiaryAutofill-License/1"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    request = urllib.request.Request(
        config.server_url + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(256 * 1024)
    except urllib.error.HTTPError as exc:
        raise LicenseError(f"Сервер лицензий вернул HTTP {exc.code}") from exc
    except OSError as exc:
        raise LicenseError("Не удалось связаться с сервером лицензий") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise LicenseError("Сервер лицензий вернул повреждённый ответ") from exc
    if not isinstance(payload, dict):
        raise LicenseError("Сервер лицензий вернул неверный формат")
    return payload


def begin_monthly_payment(config: LicenseRuntimeConfig | None = None) -> dict:
    config = config or runtime_config()
    payload = _json_request(
        config,
        "POST",
        "/api/orders",
        body={"plan": config.default_plan, "machine_hash": machine_fingerprint()},
    )
    _save_pending_order(payload)
    return payload


def refresh_paid_order(config: LicenseRuntimeConfig | None = None) -> LicenseStatus:
    config = config or runtime_config()
    order = _load_pending_order()
    order_id = str(order["order_id"])
    token = str(order["order_access_token"])
    status = _json_request(config, "GET", f"/api/orders/{order_id}/status", bearer=token)
    order_status = str(status.get("status") or "").strip().lower()
    trusted_now = None
    try:
        trusted_now = _parse_utc(str(status.get("server_time") or ""))
    except LicenseError:
        pass
    if order_status in {"cancelled", "canceled", "expired", "failed", "refunded"}:
        discard_pending_order()
        raise PaymentTerminalError("Предыдущий счёт больше недействителен. Создайте новый.")
    if order_status not in {"paid", "license_issued"}:
        raise PaymentPendingError("Оплата ещё не подтверждена")
    machine = machine_fingerprint()
    try:
        _json_request(
            config,
            "POST",
            f"/api/orders/{order_id}/activate-machine",
            body={"machine_hash": machine},
            bearer=token,
        )
    except LicenseError as exc:
        if "HTTP 409" not in str(exc):
            raise
    document = _json_request(
        config,
        "POST",
        f"/api/orders/{order_id}/license",
        body={"machine_hash": machine},
        bearer=token,
    )
    # Persist a long-lived recovery credential if Windows allows it, but never
    # make an already-captured payment depend on a transient DPAPI/disk failure.
    # The pending order token remains untouched until active recovery storage
    # succeeds, so there is always at least one retry path.
    active_recovery_saved = False
    try:
        _save_active_order(order)
        active_recovery_saved = True
    except (LicenseError, OSError):
        pass
    try:
        result = save_license(document, config, trusted_now=trusted_now)
    except LicenseExpiredError:
        # This can happen when an old paid order file survived a previous
        # successful activation. Server-confirmed expiry is the one safe case
        # where the stale order may be cleared and renewal may proceed.
        discard_pending_order()
        _discard_active_order_if_matches(order_id)
        raise
    if active_recovery_saved:
        _clear_pending_order_best_effort()
    return result


def recover_paid_license(config: LicenseRuntimeConfig | None = None) -> LicenseStatus:
    config = config or runtime_config()

    # First recover directly from the signed local entitlement. This path does
    # not require a surviving order token and exists specifically to prevent a
    # legitimate paid user from being asked to pay again after local clock
    # state damage.
    try:
        document = _load_license_document()
    except (FileNotFoundError, LicenseError):
        document = None
    if isinstance(document, dict) and _locally_trusted_paid_document(document, config):
        try:
            repaired = _repair_paid_clock_from_server(document, config)
            if repaired.active:
                return repaired
        except LicenseError:
            pass

    try:
        order = _load_active_order()
    except LicenseError as exc:
        raise PaidLicenseRecoveryError(
            "Не удалось проверить уже оплаченную лицензию. Новый платёж не нужен; повторите проверку позже."
        ) from exc
    order_id = str(order["order_id"])
    token = str(order["order_access_token"])
    try:
        status = _json_request(
            config,
            "GET",
            f"/api/orders/{order_id}/status",
            bearer=token,
        )
        order_status = str(status.get("status") or "").strip().lower()
        trusted_now = None
        try:
            trusted_now = _parse_utc(str(status.get("server_time") or ""))
        except LicenseError:
            pass
        if order_status not in {"paid", "license_issued"}:
            raise PaidLicenseRecoveryError(
                "Сервер не подтвердил действующую оплаченную лицензию"
            )
        machine = machine_fingerprint()
        document = _json_request(
            config,
            "POST",
            f"/api/orders/{order_id}/license",
            body={"machine_hash": machine},
            bearer=token,
        )
        try:
            return save_license(document, config, trusted_now=trusted_now)
        except LicenseExpiredError:
            # The server confirmed the old entitlement itself, so it is safe to
            # persist that signed expired state and allow a genuinely new payment.
            _atomic_write_text(
                license_path(),
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
            for path in (_active_order_path(), _active_order_backup_path()):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
    except LicenseExpiredError:
        raise
    except PaidLicenseRecoveryError:
        raise
    except LicenseError as exc:
        raise PaidLicenseRecoveryError(
            "Не удалось восстановить уже оплаченную лицензию. Повторная оплата не требуется."
        ) from exc


def activate_owner(bootstrap_code: str, config: LicenseRuntimeConfig | None = None) -> LicenseStatus:
    config = config or runtime_config()
    code = str(bootstrap_code or "").strip()
    if not code:
        raise LicenseError("Код активации пуст")
    document = _json_request(
        config,
        "POST",
        "/api/owner/license",
        body={"bootstrap_code": code, "machine_hash": machine_fingerprint()},
    )
    return save_license(document, config)


def discard_pending_order() -> None:
    errors = []
    for path in _pending_order_paths():
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(exc)
    if errors:
        raise LicenseError("Не удалось удалить старый заказ") from errors[-1]


def pending_payment_details() -> dict | None:
    exists = False
    for path in _pending_order_paths():
        try:
            if path.is_file():
                exists = True
                break
        except OSError:
            exists = True
            break
    if not exists:
        return None
    try:
        payload = _load_pending_order()
        order_id = str(payload.get("order_id") or "").strip()
        payment_url = str(payload.get("payment_url") or "").strip()
        amount_rub = int(payload.get("amount_rub") or 0)
        if not order_id or not payment_url or amount_rub <= 0:
            raise ValueError("incomplete order")
    except Exception as exc:
        if isinstance(exc, LicenseError):
            raise
        raise LicenseError(
            "Сохранённый счёт повреждён. Новый платёж не создан, чтобы исключить повторную оплату."
        ) from exc
    return {
        "order_id": order_id,
        "payment_url": payment_url,
        "amount_rub": amount_rub,
    }
