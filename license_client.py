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


def _pending_order_path() -> Path:
    return _runtime_dir() / "license-order.json"


def _active_order_path() -> Path:
    return _runtime_dir() / "license-active-order.json"


def _clock_path() -> Path:
    return _runtime_dir() / "license-clock.json"


def _owner_marker_path() -> Path:
    base = os.environ.get("APPDATA", "").strip()
    root = Path(base) if base else _runtime_dir().parent
    return root / "MedicalDiaryAutofill" / "owner-entitlement.marker"


def _install_id_path() -> Path:
    return _runtime_dir() / "license-install-id.txt"


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


def machine_fingerprint() -> str:
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
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _parse_utc(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    result = datetime.fromisoformat(raw)
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


def _read_clock_state() -> datetime | None:
    path = _clock_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LicenseError("license clock state is unreadable") from exc
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
    _atomic_write_text(
        _clock_path(),
        json.dumps({"schema": 2, "protected": protected}, ensure_ascii=False) + "\n",
    )


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

    _validate_clock(now, require_initialized=not allow_uninitialized_clock)
    valid_from = _parse_utc(str(payload.get("valid_from") or ""))
    valid_until = _parse_utc(str(payload.get("valid_until") or ""))
    if now < valid_from:
        raise LicenseError("license is not valid yet")
    if now > valid_until:
        return LicenseStatus(False, "expired", "Срок лицензии истёк", plan, valid_until)
    if not machine_allowed:
        raise LicenseError("license is not valid for this computer")

    _validate_paid_calendar_period(str(document.get("schema") or ""), payload, valid_until)
    _record_clock(now)
    return LicenseStatus(
        True,
        "paid",
        "Лицензия активна",
        plan,
        valid_until,
        False,
    )


def current_status(config: LicenseRuntimeConfig | None = None) -> LicenseStatus:
    config = config or runtime_config()
    configured = bool(config.server_url and config.public_key_b64)
    if not configured:
        if config.required:
            return LicenseStatus(False, "misconfigured", "Лицензирование не настроено в сборке")
        return LicenseStatus(True, "development", "Лицензирование пока не включено в этой сборке")
    owner_marker = _has_owner_marker()
    try:
        document = json.loads(license_path().read_text(encoding="utf-8"))
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
    except Exception:
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
        return _evaluate_document(document, config)
    except OwnerReactivationRequired as exc:
        return _owner_reactivation_status(str(exc))
    except LicenseError as exc:
        if owner_marker:
            return _owner_reactivation_status(
                "Требуется повторная активация лицензии"
            )
        if _has_active_order_credentials():
            return _paid_recovery_status(
                "Требуется проверить уже оплаченную лицензию"
            )
        return LicenseStatus(False, "invalid", str(exc))


def save_license(document: dict, config: LicenseRuntimeConfig | None = None) -> LicenseStatus:
    config = config or runtime_config()
    # A license returned by the trusted server is a safe point to rebuild
    # local anti-rollback state. Existing clock corruption must never strand
    # an already-paid user after successful server verification.
    try:
        status = _evaluate_document(document, config, allow_uninitialized_clock=True)
    except LicenseError:
        try:
            _clock_path().unlink(missing_ok=True)
        except OSError:
            pass
        status = _evaluate_document(document, config, allow_uninitialized_clock=True)
    if not status.active:
        if status.mode == "expired":
            raise LicenseExpiredError(status.message)
        raise LicenseError(status.message)
    _atomic_write_text(
        license_path(),
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
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


def _save_pending_order(payload: dict) -> None:
    _store_order_credentials(_pending_order_path(), payload, include_payment=True)


def _load_pending_order() -> dict:
    return _load_order_credentials(
        _pending_order_path(),
        "Нет сохранённого заказа на оплату",
    )


def _save_active_order(order: dict) -> None:
    _store_order_credentials(_active_order_path(), order, include_payment=False)


def _load_active_order() -> dict:
    return _load_order_credentials(
        _active_order_path(),
        "Нет данных для восстановления оплаченной лицензии",
    )


def _has_active_order_credentials() -> bool:
    try:
        _load_active_order()
        return True
    except LicenseError:
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
    if order_status in {"cancelled", "canceled", "expired", "failed", "refunded"}:
        discard_pending_order()
        raise LicenseError("Предыдущий счёт больше недействителен. Создайте новый.")
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
    # Persist the recovery credential before local license state. If a disk or
    # clock-state error happens after payment, the user can retry without paying again.
    _save_active_order(order)
    result = save_license(document, config)
    try:
        _pending_order_path().unlink(missing_ok=True)
    except OSError:
        pass
    return result


def recover_paid_license(config: LicenseRuntimeConfig | None = None) -> LicenseStatus:
    config = config or runtime_config()
    order = _load_active_order()
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
        return save_license(document, config)
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
    try:
        _pending_order_path().unlink(missing_ok=True)
    except OSError as exc:
        raise LicenseError("Не удалось удалить старый заказ") from exc


def pending_payment_details() -> dict | None:
    try:
        payload = json.loads(_pending_order_path().read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "order_id": str(payload.get("order_id") or ""),
        "payment_url": str(payload.get("payment_url") or ""),
        "amount_rub": int(payload.get("amount_rub") or 0),
    }
