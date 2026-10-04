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
import license_ui as lui


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signed_document(private_key, payload: dict, *, schema: str = lc.LICENSE_SCHEMA) -> dict:
    signature = private_key.sign(canonical(payload))
    return {
        "schema": schema,
        "license": {
            "payload": payload,
            "signature_alg": "ed25519",
            "signature": base64.b64encode(signature).decode("ascii"),
        },
    }


def payload(
    machine: str,
    *,
    days: int | None = None,
    product: str = lc.PRODUCT_ID,
    owner: bool = False,
    issued_at: datetime | None = None,
) -> dict:
    now = (issued_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    valid_until = lc._add_calendar_month(now) if days is None else now + timedelta(days=days)
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
        "valid_until": valid_until.isoformat().replace("+00:00", "Z"),
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
        os.environ["APPDATA"] = str(Path(td) / "Roaming")
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
        lc._windows_machine_guid = lambda: ""
        lc._install_id = lambda: "install-c"
        stable_c = lc.machine_fingerprint()
        assert stable_c == stable_a, "transient MachineGuid read failure changed paid-license identity"
        # If the very first MachineGuid read fails, the chosen fallback
        # identity is pinned and must not jump to a different fingerprint later
        # when MachineGuid becomes readable.
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        old_guid = lc._windows_machine_guid
        old_install = lc._install_id
        lc._windows_machine_guid = lambda: ""
        lc._install_id = lambda: "first-run-fallback"
        first_fallback = lc.machine_fingerprint()
        assert lc._machine_fingerprint_cache_path().exists()
        assert lc._machine_fingerprint_backup_path().exists()
        lc._windows_machine_guid = lambda: "guid-became-readable"
        lc._install_id = lambda: "different-install-id"
        assert lc.machine_fingerprint() == first_fallback
        lc._windows_machine_guid = old_guid
        lc._install_id = old_install

        paid = signed_document(private, payload(machine))
        assert lc.save_license(paid, config).active
        assert lc.current_status(config).mode == "paid"

        # Existing v1 licenses were sold as fixed 31-day periods. They must
        # remain usable until their originally signed expiration after upgrade.
        legacy_v1 = signed_document(
            private,
            payload(machine, days=31),
            schema=lc.LEGACY_LICENSE_SCHEMA,
        )
        legacy_status = lc._evaluate_document(legacy_v1, config)
        assert legacy_status.active and legacy_status.mode == "paid"

        # Paid anti-rollback state is redundant. Losing/corrupting one copy
        # must transparently heal from the other without blocking the doctor.
        clock_primary = lc._clock_path().read_text(encoding="utf-8")
        assert lc._clock_backup_path().exists()
        lc._clock_path().unlink()
        healed = lc.current_status(config)
        assert healed.active and healed.mode == "paid"
        assert lc._clock_path().exists()

        lc._clock_path().write_text("{broken", encoding="utf-8")
        healed = lc.current_status(config)
        assert healed.active and healed.mode == "paid"

        # If both clock copies are lost, a valid signed paid entitlement can
        # repair itself from trusted server time without any order/recovery token.
        for path in (
            lc._clock_path(),
            lc._clock_backup_path(),
            lc._active_order_path(),
            lc._active_order_backup_path(),
        ):
            path.unlink(missing_ok=True)
        old_json_request = lc._json_request
        old_machine_fingerprint = lc.machine_fingerprint
        health_calls = []
        try:
            lc.machine_fingerprint = lambda: machine

            def _health_request(_config, method, path, *, body=None, bearer=""):
                health_calls.append((method, path, body, bearer))
                if method == "GET" and path == "/health":
                    return {
                        "status": "ok",
                        "product_id": lc.PRODUCT_ID,
                        "public_key_b64": config.public_key_b64,
                        "server_time": datetime.now(timezone.utc).isoformat(),
                    }
                raise AssertionError((method, path, body, bearer))

            lc._json_request = _health_request
            repaired = lc.current_status(config)
            assert repaired.active and repaired.mode == "paid"
            assert lc._clock_path().exists()
            assert lc._clock_backup_path().exists()
        finally:
            lc._json_request = old_json_request
            lc.machine_fingerprint = old_machine_fingerprint
        assert health_calls == [("GET", "/health", None, "")]

        # If both clock copies are gone and the server is temporarily offline,
        # the signed paid entitlement suppresses new-payment UX instead of being
        # treated as a fresh unlicensed installation.
        lc._clock_path().unlink(missing_ok=True)
        lc._clock_backup_path().unlink(missing_ok=True)
        old_json_request = lc._json_request
        old_machine_fingerprint = lc.machine_fingerprint
        try:
            lc.machine_fingerprint = lambda: machine

            def _offline_health(*args, **kwargs):
                raise lc.LicenseError("server temporarily unavailable")

            lc._json_request = _offline_health
            recovery = lc.current_status(config)
            assert not recovery.active
            assert recovery.mode == "paid_recovery"
            manager = lui._manager_state(recovery)
            assert not manager["show_payment"]
            assert manager["show_recovery"]
        finally:
            lc._json_request = old_json_request
            lc.machine_fingerprint = old_machine_fingerprint

        # Restore ordinary clock state for independent regressions below.
        lc._clock_path().write_text(clock_primary, encoding="utf-8")
        lc._clock_backup_path().write_text(clock_primary, encoding="utf-8")

        # A stale local payment order can always be discarded and replaced.
        lc._save_pending_order({
            "order_id": "00000000-0000-0000-0000-000000000099",
            "order_access_token": "token",
            "payment_url": "https://pay.example.com/old",
            "amount_rub": 1,
        })
        assert lc.pending_payment_details() is not None
        assert lc._pending_order_backup_path().exists()
        # Losing or corrupting the primary order file before license claim must
        # recover the same already-created invoice from the roaming DPAPI backup.
        lc._pending_order_path().unlink()
        recovered_pending = lc.pending_payment_details()
        assert recovered_pending and recovered_pending["order_id"] == "00000000-0000-0000-0000-000000000099"
        assert lc._pending_order_path().exists()
        lc._pending_order_path().write_text("{broken", encoding="utf-8")
        recovered_pending = lc.pending_payment_details()
        assert recovered_pending and recovered_pending["order_id"] == "00000000-0000-0000-0000-000000000099"
        lc.discard_pending_order()
        assert lc.pending_payment_details() is None
        assert not lc._pending_order_backup_path().exists()
        lc._pending_order_path().write_text("{broken", encoding="utf-8")
        try:
            lc.pending_payment_details()
            raise AssertionError("damaged pending order was treated as no payment")
        except lc.LicenseError:
            pass
        lc._pending_order_path().unlink(missing_ok=True)

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

        # A signed paid license is still invalid if its period is a fixed
        # number of days instead of exactly one calendar month.
        april_30 = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
        fixed_31_day_payload = payload(machine, days=31, issued_at=april_30)
        try:
            lc._validate_paid_calendar_period(
                lc.LICENSE_SCHEMA,
                fixed_31_day_payload,
                lc._parse_utc(fixed_31_day_payload["valid_until"]),
            )
            raise AssertionError("fixed 31-day license bypassed calendar-month contract")
        except lc.LicenseError:
            pass

        annual = signed_document(private, payload(machine, days=365))
        try:
            lc._evaluate_document(annual, config)
            raise AssertionError("annual paid license bypassed monthly contract")
        except lc.LicenseError:
            pass

        # Successful payment must leave a DPAPI/HMAC-protected recovery
        # credential so local license/clock damage never forces a second charge.
        recovery_order = {
            "order_id": "00000000-0000-0000-0000-000000000001",
            "order_access_token": "R" * 48,
            "payment_url": "https://pay.example.com/recovery",
            "amount_rub": 100,
        }
        lc._save_pending_order(recovery_order)
        old_json_request = lc._json_request
        old_machine_fingerprint = lc.machine_fingerprint
        recovery_calls = []
        try:
            lc.machine_fingerprint = lambda: machine

            def _paid_request(_config, method, path, *, body=None, bearer=""):
                recovery_calls.append((method, path, body, bearer))
                if method == "GET" and path.endswith("/status"):
                    return {
                        "status": "license_issued",
                        "amount_rub": 100,
                        "server_time": paid["license"]["payload"]["issued_at"],
                    }
                if method == "POST" and path.endswith("/activate-machine"):
                    return {"activated": True, "machine_hash": machine}
                if method == "POST" and path.endswith("/license"):
                    return paid
                raise AssertionError((method, path, body, bearer))

            lc._json_request = _paid_request
            paid_status = lc.refresh_paid_order(config)
            assert paid_status.active and paid_status.mode == "paid"
            assert lc._active_order_path().exists()
            assert lc._active_order_backup_path().exists()
            assert not lc._pending_order_path().exists()
            assert not lc._pending_order_backup_path().exists()

            active_primary = lc._active_order_path().read_text(encoding="utf-8")
            lc._active_order_path().unlink()
            backup_loaded = lc._load_active_order()
            assert backup_loaded["order_id"] == recovery_order["order_id"]
            lc._active_order_path().write_text("{broken", encoding="utf-8")
            backup_loaded = lc._load_active_order()
            assert backup_loaded["order_id"] == recovery_order["order_id"]
            lc._active_order_path().write_text(active_primary, encoding="utf-8")

            lc.license_path().write_text("{broken", encoding="utf-8")
            lc._clock_path().write_text("{broken", encoding="utf-8")
            recovery_needed = lc.current_status(config)
            assert not recovery_needed.active
            assert recovery_needed.mode == "paid_recovery"

            restored = lc.recover_paid_license(config)
            assert restored.active and restored.mode == "paid"
            assert lc.current_status(config).active
            assert lc.current_status(config).mode == "paid"
        finally:
            lc._json_request = old_json_request
            lc.machine_fingerprint = old_machine_fingerprint
        assert recovery_calls

        # A locally expired-looking paid license with recovery credentials
        # must be revalidated before any new payment is offered.
        expired_payload = payload(
            machine,
            issued_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        expired_document = signed_document(private, expired_payload)
        lc.license_path().write_text(
            json.dumps(expired_document, ensure_ascii=False),
            encoding="utf-8",
        )
        lc._clock_path().unlink(missing_ok=True)
        lc._record_clock(datetime.now(timezone.utc))
        expired_local = lc.current_status(config)
        assert not expired_local.active
        assert expired_local.mode == "paid_recovery"
        assert lc.save_license(paid, config).active

        # Trusted server time must let a freshly paid entitlement activate even
        # when the workstation clock is far behind the server.
        future_server_time = datetime.now(timezone.utc) + timedelta(days=365)
        future_paid = signed_document(
            private,
            payload(machine, issued_at=future_server_time),
        )
        future_order = {
            "order_id": "00000000-0000-0000-0000-000000000002",
            "order_access_token": "S" * 48,
            "payment_url": "https://pay.example.com/future",
            "amount_rub": 100,
        }
        lc._save_pending_order(future_order)
        old_json_request = lc._json_request
        old_machine_fingerprint = lc.machine_fingerprint
        try:
            lc.machine_fingerprint = lambda: machine

            def _future_request(_config, method, path, *, body=None, bearer=""):
                if method == "GET" and path.endswith("/status"):
                    return {
                        "status": "paid",
                        "amount_rub": 100,
                        "server_time": future_server_time.isoformat(),
                    }
                if method == "POST" and path.endswith("/activate-machine"):
                    return {"activated": True, "machine_hash": machine}
                if method == "POST" and path.endswith("/license"):
                    return future_paid
                raise AssertionError((method, path, body, bearer))

            lc._json_request = _future_request
            future_status = lc.refresh_paid_order(config)
            assert future_status.active and future_status.mode == "paid"
        finally:
            lc._json_request = old_json_request
            lc.machine_fingerprint = old_machine_fingerprint

        # Rolling deployment / malformed server timestamp must never crash
        # activation after money has already been captured. Missing or invalid
        # server_time falls back safely instead of escaping as ValueError.
        for server_time_value in (None, "", "not-a-timestamp"):
            fallback_order = {
                "order_id": "00000000-0000-0000-0000-000000000020",
                "order_access_token": "U" * 48,
                "payment_url": "https://pay.example.com/fallback",
                "amount_rub": 100,
            }
            lc._save_pending_order(fallback_order)
            old_json_request = lc._json_request
            old_machine_fingerprint = lc.machine_fingerprint
            try:
                lc.machine_fingerprint = lambda: machine

                def _fallback_request(_config, method, path, *, body=None, bearer=""):
                    if method == "GET" and path.endswith("/status"):
                        response = {"status": "paid", "amount_rub": 100}
                        if server_time_value is not None:
                            response["server_time"] = server_time_value
                        return response
                    if method == "POST" and path.endswith("/activate-machine"):
                        return {"activated": True, "machine_hash": machine}
                    if method == "POST" and path.endswith("/license"):
                        return paid
                    raise AssertionError((method, path, body, bearer))

                lc._json_request = _fallback_request
                fallback_status = lc.refresh_paid_order(config)
                assert fallback_status.active and fallback_status.mode == "paid"
            finally:
                lc._json_request = old_json_request
                lc.machine_fingerprint = old_machine_fingerprint
            lc._pending_order_path().unlink(missing_ok=True)

        try:
            lc._parse_utc("not-a-timestamp")
            raise AssertionError("malformed timestamp escaped normalized LicenseError handling")
        except lc.LicenseError:
            pass

        # Restore ordinary current-time paid state for the remaining regressions.
        lc._active_order_path().unlink(missing_ok=True)
        lc._clock_path().unlink(missing_ok=True)
        assert lc.save_license(paid, config).active
        lc._save_active_order(recovery_order)

        # If a stale pending file survived the first activation, a server-
        # confirmed expired signed license must clean both stale order records.
        stale_order = {
            "order_id": "00000000-0000-0000-0000-000000000003",
            "order_access_token": "T" * 48,
            "payment_url": "https://pay.example.com/stale",
            "amount_rub": 100,
        }
        stale_expired = signed_document(
            private,
            payload(machine, issued_at=datetime.now(timezone.utc) - timedelta(days=60)),
        )
        lc._save_pending_order(stale_order)
        lc._save_active_order(stale_order)
        old_json_request = lc._json_request
        old_machine_fingerprint = lc.machine_fingerprint
        try:
            lc.machine_fingerprint = lambda: machine

            def _stale_request(_config, method, path, *, body=None, bearer=""):
                if method == "GET" and path.endswith("/status"):
                    return {
                        "status": "license_issued",
                        "amount_rub": 100,
                        "server_time": datetime.now(timezone.utc).isoformat(),
                    }
                if method == "POST" and path.endswith("/activate-machine"):
                    return {"activated": True, "machine_hash": machine}
                if method == "POST" and path.endswith("/license"):
                    return stale_expired
                raise AssertionError((method, path))

            lc._json_request = _stale_request
            try:
                lc.refresh_paid_order(config)
                raise AssertionError("expired stale order was accepted")
            except lc.LicenseExpiredError:
                pass
            assert not lc._pending_order_path().exists()
            assert not lc._pending_order_backup_path().exists()
            assert not lc._active_order_path().exists()
        finally:
            lc._json_request = old_json_request
            lc.machine_fingerprint = old_machine_fingerprint

        # Restore an active recovery credential for later recovery-UI tests.
        lc._save_active_order(recovery_order)
        lc._clock_path().unlink(missing_ok=True)
        assert lc.save_license(paid, config).active

        # A network/recovery failure for an already-paid entitlement must not
        # create a fresh payment order.
        old_runtime_config = lui.runtime_config
        old_current_status = lui.current_status
        old_recover = lui.recover_paid_license
        old_begin_payment = lui.begin_monthly_payment
        old_showwarning = lui.messagebox.showwarning
        recovery_ui_calls = {"payment": 0, "warning": 0}
        try:
            lui.runtime_config = lambda: config
            lui.current_status = lambda _config: lc.LicenseStatus(
                False,
                "paid_recovery",
                "recovery required",
                "doctor_start",
                None,
                False,
            )
            lui.recover_paid_license = lambda _config: (_ for _ in ()).throw(
                lc.PaidLicenseRecoveryError("temporary server outage")
            )
            lui.begin_monthly_payment = lambda *args, **kwargs: (
                recovery_ui_calls.__setitem__("payment", recovery_ui_calls["payment"] + 1)
                or (_ for _ in ()).throw(AssertionError("paid recovery created a second charge"))
            )
            lui.messagebox.showwarning = lambda *args, **kwargs: recovery_ui_calls.__setitem__(
                "warning", recovery_ui_calls["warning"] + 1
            )
            assert not lui.ensure_license(None, interactive=True)
            assert recovery_ui_calls["payment"] == 0
            assert recovery_ui_calls["warning"] == 1
        finally:
            lui.runtime_config = old_runtime_config
            lui.current_status = old_current_status
            lui.recover_paid_license = old_recover
            lui.begin_monthly_payment = old_begin_payment
            lui.messagebox.showwarning = old_showwarning

        # Corrupt pending payment state must block a fresh charge rather than
        # being silently treated as no existing invoice.
        old_pending_details = lui.pending_payment_details
        old_begin_payment = lui.begin_monthly_payment
        old_showwarning = lui.messagebox.showwarning
        damaged_pending_calls = {"payment": 0, "warning": 0}
        try:
            lui.pending_payment_details = lambda: (_ for _ in ()).throw(
                lc.LicenseError("damaged pending order")
            )
            lui.begin_monthly_payment = lambda *args, **kwargs: (
                damaged_pending_calls.__setitem__("payment", damaged_pending_calls["payment"] + 1)
                or (_ for _ in ()).throw(AssertionError("damaged pending order created a new charge"))
            )
            lui.messagebox.showwarning = lambda *args, **kwargs: damaged_pending_calls.__setitem__(
                "warning", damaged_pending_calls["warning"] + 1
            )
            assert lui._payment_flow(None, config) is None
            assert damaged_pending_calls == {"payment": 0, "warning": 1}
        finally:
            lui.pending_payment_details = old_pending_details
            lui.begin_monthly_payment = old_begin_payment
            lui.messagebox.showwarning = old_showwarning

        # A server-confirmed expired stale order is the only old-order case
        # that may unlock exactly one fresh renewal invoice.
        old_pending_details = lui.pending_payment_details
        old_refresh_paid = lui.refresh_paid_order
        old_begin_payment = lui.begin_monthly_payment
        old_showinfo = lui.messagebox.showinfo
        old_showwarning = lui.messagebox.showwarning
        old_webopen = lui.webbrowser.open
        renewal_calls = {"payment": 0, "refresh": 0}
        try:
            lui.pending_payment_details = lambda: {
                "order_id": "expired-order",
                "payment_url": "https://pay.example.com/expired",
                "amount_rub": 100,
            }

            def _renewal_refresh(_config):
                renewal_calls["refresh"] += 1
                if renewal_calls["refresh"] == 1:
                    raise lc.LicenseExpiredError("expired")
                return lc.LicenseStatus(
                    True,
                    "paid",
                    "Лицензия активна",
                    "doctor_start",
                    datetime.now(timezone.utc) + timedelta(days=28),
                    False,
                )

            lui.refresh_paid_order = _renewal_refresh
            lui.begin_monthly_payment = lambda _config: (
                renewal_calls.__setitem__("payment", renewal_calls["payment"] + 1)
                or {
                    "order_id": "new-order",
                    "payment_url": "https://pay.example.com/new",
                    "amount_rub": 100,
                }
            )
            lui.messagebox.showinfo = lambda *args, **kwargs: None
            lui.messagebox.showwarning = lambda *args, **kwargs: None
            lui.webbrowser.open = lambda *args, **kwargs: True
            renewed = lui._payment_flow(None, config)
            assert renewed and renewed.active
            assert renewal_calls == {"payment": 1, "refresh": 2}
        finally:
            lui.pending_payment_details = old_pending_details
            lui.refresh_paid_order = old_refresh_paid
            lui.begin_monthly_payment = old_begin_payment
            lui.messagebox.showinfo = old_showinfo
            lui.messagebox.showwarning = old_showwarning
            lui.webbrowser.open = old_webopen

        # A nonterminal old invoice may never be replaced merely because the
        # payment provider reconciliation is delayed.
        old_pending_details = lui.pending_payment_details
        old_refresh_paid = lui.refresh_paid_order
        old_begin_payment = lui.begin_monthly_payment
        old_showinfo = lui.messagebox.showinfo
        old_showwarning = lui.messagebox.showwarning
        old_webopen = lui.webbrowser.open
        pending_calls = {"payment": 0, "refresh": 0}
        try:
            lui.pending_payment_details = lambda: {
                "order_id": "pending-order",
                "payment_url": "https://pay.example.com/pending",
                "amount_rub": 100,
            }

            def _still_pending(_config):
                pending_calls["refresh"] += 1
                raise lc.PaymentPendingError("pending")

            lui.refresh_paid_order = _still_pending
            lui.begin_monthly_payment = lambda *args, **kwargs: (
                pending_calls.__setitem__("payment", pending_calls["payment"] + 1)
                or (_ for _ in ()).throw(AssertionError("nonterminal invoice was replaced"))
            )
            lui.messagebox.showinfo = lambda *args, **kwargs: None
            lui.messagebox.showwarning = lambda *args, **kwargs: None
            lui.webbrowser.open = lambda *args, **kwargs: True
            assert lui._payment_flow(None, config) is None
            assert pending_calls["payment"] == 0
            assert pending_calls["refresh"] >= 1
        finally:
            lui.pending_payment_details = old_pending_details
            lui.refresh_paid_order = old_refresh_paid
            lui.begin_monthly_payment = old_begin_payment
            lui.messagebox.showinfo = old_showinfo
            lui.messagebox.showwarning = old_showwarning
            lui.webbrowser.open = old_webopen

        # If a previous invoice is already paid, payment UX must claim it first
        # and must not create another invoice.
        old_pending_details = lui.pending_payment_details
        old_refresh_paid = lui.refresh_paid_order
        old_begin_payment = lui.begin_monthly_payment
        old_showinfo = lui.messagebox.showinfo
        paid_ui_calls = {"payment": 0, "refresh": 0}
        try:
            lui.pending_payment_details = lambda: {
                "order_id": recovery_order["order_id"],
                "payment_url": recovery_order["payment_url"],
                "amount_rub": 100,
            }
            lui.refresh_paid_order = lambda _config: (
                paid_ui_calls.__setitem__("refresh", paid_ui_calls["refresh"] + 1)
                or lc.LicenseStatus(
                    True,
                    "paid",
                    "Лицензия активна",
                    "doctor_start",
                    datetime.now(timezone.utc) + timedelta(days=10),
                    False,
                )
            )
            lui.begin_monthly_payment = lambda *args, **kwargs: (
                paid_ui_calls.__setitem__("payment", paid_ui_calls["payment"] + 1)
                or (_ for _ in ()).throw(AssertionError("already-paid invoice created a second charge"))
            )
            lui.messagebox.showinfo = lambda *args, **kwargs: None
            claimed = lui._payment_flow(None, config)
            assert claimed and claimed.active
            assert paid_ui_calls == {"payment": 0, "refresh": 1}
        finally:
            lui.pending_payment_details = old_pending_details
            lui.refresh_paid_order = old_refresh_paid
            lui.begin_monthly_payment = old_begin_payment
            lui.messagebox.showinfo = old_showinfo

        owner = signed_document(private, payload(machine, days=3650, owner=True))
        old_json_request = lc._json_request
        old_machine_fingerprint = lc.machine_fingerprint
        owner_activation_calls = []
        try:
            lc.machine_fingerprint = lambda: machine

            def _owner_request(_config, method, path, *, body=None, bearer=""):
                owner_activation_calls.append((method, path, body, bearer))
                assert method == "POST"
                assert path == "/api/owner/license"
                assert body == {"bootstrap_code": "owner-code", "machine_hash": machine}
                assert bearer == ""
                return owner

            lc._json_request = _owner_request
            owner_status = lc.activate_owner("owner-code", config)
        finally:
            lc._json_request = old_json_request
            lc.machine_fingerprint = old_machine_fingerprint
        assert owner_activation_calls
        assert owner_status.active and owner_status.owner_unlimited and owner_status.mode == "owner"
        assert lc._owner_marker_path().exists()

        # The owner marker lives outside the install-local license file and
        # never grants access by itself. It only forces owner-only reactivation
        # if the signed license file is lost or damaged.
        owner_license_text = lc.license_path().read_text(encoding="utf-8")
        lc.license_path().unlink()
        lost_owner = lc.current_status(config)
        assert not lost_owner.active
        assert lost_owner.mode == "owner_reactivation"
        assert lost_owner.owner_unlimited
        lc.license_path().write_text("{broken", encoding="utf-8")
        damaged_owner = lc.current_status(config)
        assert not damaged_owner.active
        assert damaged_owner.mode == "owner_reactivation"
        assert damaged_owner.owner_unlimited
        lc.license_path().write_text(owner_license_text, encoding="utf-8")

        # Owner access is intentionally independent from the paid-license
        # anti-clock state. Missing/corrupt clock data must never send the
        # owner into the subscription/payment path.
        lc._clock_path().unlink(missing_ok=True)
        owner_status = lc.current_status(config)
        assert owner_status.active and owner_status.mode == "owner" and owner_status.owner_unlimited
        lc._clock_path().write_text("{broken", encoding="utf-8")
        owner_status = lc.current_status(config)
        assert owner_status.active and owner_status.mode == "owner" and owner_status.owner_unlimited

        # If Windows/MachineGuid changes, a valid signed owner entitlement is
        # recognized as owner reactivation rather than a missing paid license.
        old_fingerprint = lc.machine_fingerprint
        lc.machine_fingerprint = lambda: "f" * 64
        try:
            reactivation = lc.current_status(config)
            assert not reactivation.active
            assert reactivation.mode == "owner_reactivation"
            assert reactivation.owner_unlimited
        finally:
            lc.machine_fingerprint = old_fingerprint

        # An already-active owner must bypass every licensing dialog and
        # every payment function on ordinary startup/generation checks.
        old_runtime_config = lui.runtime_config
        old_current_status = lui.current_status
        old_begin_payment = lui.begin_monthly_payment
        old_askyesnocancel = lui.messagebox.askyesnocancel
        try:
            lui.runtime_config = lambda: config
            lui.current_status = lambda _config: lc.LicenseStatus(
                True,
                "owner",
                "owner",
                "vip",
                None,
                True,
            )
            lui.begin_monthly_payment = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("active owner reached monthly payment")
            )
            lui.messagebox.askyesnocancel = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("active owner reached licensing dialog")
            )
            assert lui.ensure_license(None, interactive=True)
            assert lui.ensure_generation_license(None)
        finally:
            lui.runtime_config = old_runtime_config
            lui.current_status = old_current_status
            lui.begin_monthly_payment = old_begin_payment
            lui.messagebox.askyesnocancel = old_askyesnocancel

        # Public license-manager UX must stay discreet: privileged access is
        # internally recognized, but the interface only says that the license is active.
        active_private = lc.LicenseStatus(True, "owner", "internal", "vip", None, True)
        manager = lui._manager_state(active_private)
        assert manager["title"] == "Лицензия активна"
        assert manager["details"] == "Доступ активирован."
        assert not manager["show_payment"]
        assert not manager["show_activation"]
        assert lui._format_status(active_private) == "Лицензия активна."

        reactivate_private = lc.LicenseStatus(
            False,
            "owner_reactivation",
            "internal",
            "vip",
            None,
            True,
        )
        manager = lui._manager_state(reactivate_private)
        assert manager["title"] == "Требуется активация"
        assert manager["show_activation"]
        assert not manager["show_payment"]
        assert "влад" not in manager["details"].lower()
        assert "безлим" not in manager["details"].lower()

        paid_public = lc.LicenseStatus(
            True,
            "paid",
            "Лицензия активна",
            "doctor_start",
            datetime.now(timezone.utc) + timedelta(days=10),
            False,
        )
        manager = lui._manager_state(paid_public)
        assert manager["show_activation"]
        assert not manager["show_payment"]

        missing_public = lc.LicenseStatus(False, "missing", "Лицензия не активирована")
        manager = lui._manager_state(missing_public)
        assert manager["show_activation"] and manager["show_payment"]

        license_ui_text = (ROOT / "license_ui.py").read_text(encoding="utf-8").lower()
        license_client_text = (ROOT / "license_client.py").read_text(encoding="utf-8").lower()
        for forbidden_public_phrase in (
            "безлимитный доступ владельца",
            "доступ владельца",
            "код владельца",
            "суперадмин",
            "супер админ",
        ):
            assert forbidden_public_phrase not in license_ui_text
            assert forbidden_public_phrase not in license_client_text
        assert "ввести код активации" in license_ui_text
        assert "код активации пуст" in license_client_text

        window_text = (ROOT / "window_mixin.py").read_text(encoding="utf-8")
        assert 'text="Лицензия", command=self._show_license_manager' in window_text
        assert "show_license_manager(self.root)" in window_text

        # Entering an activation code from the manager must use the same secure
        # server verification and return an active license without touching payment.
        old_activate_owner = lui.activate_owner
        old_askstring = lui.simpledialog.askstring
        old_showinfo = lui.messagebox.showinfo
        old_showerror = lui.messagebox.showerror
        old_begin_payment = lui.begin_monthly_payment
        manager_calls = {"activation": 0, "payment": 0}
        try:
            lui.simpledialog.askstring = lambda *args, **kwargs: "activation-code"
            lui.activate_owner = lambda code, _config: (
                manager_calls.__setitem__("activation", manager_calls["activation"] + 1)
                or lc.LicenseStatus(True, "owner", "internal", "vip", None, True)
            )
            lui.begin_monthly_payment = lambda *args, **kwargs: (
                manager_calls.__setitem__("payment", manager_calls["payment"] + 1)
                or (_ for _ in ()).throw(AssertionError("activation code reached payment"))
            )
            lui.messagebox.showinfo = lambda *args, **kwargs: None
            lui.messagebox.showerror = lambda *args, **kwargs: None
            manager_status = lui._activate_code(None, config)
            assert manager_status and manager_status.active
            assert manager_calls == {"activation": 1, "payment": 0}
        finally:
            lui.activate_owner = old_activate_owner
            lui.simpledialog.askstring = old_askstring
            lui.messagebox.showinfo = old_showinfo
            lui.messagebox.showerror = old_showerror
            lui.begin_monthly_payment = old_begin_payment

        # The owner-reactivation UI has no route to monthly payment.
        old_runtime_config = lui.runtime_config
        old_current_status = lui.current_status
        old_activate_owner = lui.activate_owner
        old_begin_payment = lui.begin_monthly_payment
        old_askstring = lui.simpledialog.askstring
        old_askyesnocancel = lui.messagebox.askyesnocancel
        old_showinfo = lui.messagebox.showinfo
        old_showerror = lui.messagebox.showerror
        old_retry = lui.messagebox.askretrycancel
        calls = {"payment": 0, "owner": 0}
        try:
            lui.runtime_config = lambda: config
            lui.current_status = lambda _config: lc.LicenseStatus(
                False,
                "owner_reactivation",
                "owner reactivation required",
                "vip",
                None,
                True,
            )
            lui.simpledialog.askstring = lambda *args, **kwargs: "owner-code"
            lui.activate_owner = lambda code, _config: (
                calls.__setitem__("owner", calls["owner"] + 1)
                or lc.LicenseStatus(True, "owner", "owner", "vip", None, True)
            )
            def _payment_forbidden(*args, **kwargs):
                calls["payment"] += 1
                raise AssertionError("owner reactivation reached monthly payment")
            lui.begin_monthly_payment = _payment_forbidden
            lui.messagebox.askyesnocancel = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("owner reactivation reached paid-license chooser")
            )
            lui.messagebox.showinfo = lambda *args, **kwargs: None
            lui.messagebox.showerror = lambda *args, **kwargs: None
            lui.messagebox.askretrycancel = lambda *args, **kwargs: False
            assert lui.ensure_license(None, interactive=True)
            assert calls == {"payment": 0, "owner": 1}
        finally:
            lui.runtime_config = old_runtime_config
            lui.current_status = old_current_status
            lui.activate_owner = old_activate_owner
            lui.begin_monthly_payment = old_begin_payment
            lui.simpledialog.askstring = old_askstring
            lui.messagebox.askyesnocancel = old_askyesnocancel
            lui.messagebox.showinfo = old_showinfo
            lui.messagebox.showerror = old_showerror
            lui.messagebox.askretrycancel = old_retry

        # Installer contract: user-owned licensing state shares the production
        # LocalAppData directory and must never be listed for install/uninstall
        # deletion.
        installer_text = (ROOT / "installer" / "MedicalDiaryAutofill.iss").read_text(encoding="utf-8")
        assert "DefaultDirName={localappdata}\\MedicalDiaryAutofill" in installer_text
        assert "license.json" not in installer_text
        assert "license-clock.json" not in installer_text
        assert "license-active-order.json" not in installer_text
        assert "license-machine-fingerprint.json" not in installer_text
        assert "paid-entitlement-recovery.json" not in installer_text
        assert "owner-entitlement.marker" not in installer_text

        # Restore a clean paid-license clock state for the independent rollback
        # regression below; owner deliberately ignored the damaged clock above.
        lc._clock_path().unlink(missing_ok=True)
        assert lc.save_license(paid, config).active

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
