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
        original_windows_machine_guid = lc._windows_machine_guid
        original_windows_smbios_uuid = lc._windows_smbios_uuid
        original_install_id = lc._install_id
        old_guid = original_windows_machine_guid
        old_install = original_install_id
        # Keep the pre-existing MachineGuid-only regression cases deterministic;
        # dedicated clone-guard coverage below exercises SMBIOS-backed v2.
        lc._windows_smbios_uuid = lambda: ""
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._windows_machine_guid = lambda: "stable-guid"
        lc._install_id = lambda: "install-a"
        stable_a = lc.machine_fingerprint()
        lc._install_id = lambda: "install-b"
        stable_b = lc.machine_fingerprint()
        assert stable_a == stable_b
        lc._windows_machine_guid = lambda: ""
        lc._install_id = lambda: "install-c"
        old_windows_runtime = lc._is_windows_runtime
        lc._is_windows_runtime = lambda: True
        try:
            lc.machine_fingerprint()
            raise AssertionError("Windows trusted a cached fingerprint without current MachineGuid evidence")
        except lc.MachineIdentityUnavailableError:
            pass
        finally:
            lc._is_windows_runtime = old_windows_runtime
        # On Windows, a missing MachineGuid must fail closed instead of minting
        # a user-controlled fallback identity. Once MachineGuid becomes readable,
        # the canonical Windows fingerprint is derived and cached.
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        old_guid = lc._windows_machine_guid
        old_install = lc._install_id
        old_windows_runtime = lc._is_windows_runtime
        lc._is_windows_runtime = lambda: True
        lc._windows_machine_guid = lambda: ""
        lc._install_id = lambda: "first-run-fallback"
        try:
            lc.machine_fingerprint()
            raise AssertionError("Windows accepted a user-controlled fallback machine identity")
        except lc.MachineIdentityUnavailableError:
            pass
        assert not lc._machine_fingerprint_cache_path().exists()
        assert not lc._machine_fingerprint_backup_path().exists()

        lc._windows_machine_guid = lambda: "guid-became-readable"
        secure_windows_fingerprint = lc.machine_fingerprint()
        expected_windows_fingerprint = __import__("hashlib").sha256(
            b"windows-machine-guid-v1|guid-became-readable"
        ).hexdigest()
        assert secure_windows_fingerprint == expected_windows_fingerprint

        # Win32's C literal 'RSMB' is DWORD 0x52534D42. Lock the exact
        # provider value so a byte-order reversal cannot silently disable the
        # hardware anchor on every real Windows machine.
        assert lc._RSMB_PROVIDER_SIGNATURE == 0x52534D42
        if os.name == "nt":
            live_smbios_uuid = original_windows_smbios_uuid()
            assert len(live_smbios_uuid) == 32
            assert all(ch in "0123456789abcdef" for ch in live_smbios_uuid)

        # Parse SMBIOS System Information (type 1) without depending on WMI.
        synthetic_uuid = bytes.fromhex("00112233445566778899aabbccddeeff")
        synthetic_type1 = (
            bytes([1, 24, 0, 0])
            + bytes([1, 2, 3, 4])
            + synthetic_uuid
            + b"\x00\x00"
        )
        synthetic_raw = (
            bytes([0, 3, 2, 0])
            + len(synthetic_type1).to_bytes(4, "little")
            + synthetic_type1
        )
        assert lc._parse_raw_smbios_uuid(synthetic_raw) == synthetic_uuid.hex()
        zero_uuid_type1 = (
            bytes([1, 24, 0, 0])
            + bytes([1, 2, 3, 4])
            + b"\x00" * 16
            + b"\x00\x00"
        )
        zero_uuid_raw = (
            bytes([0, 3, 2, 0])
            + len(zero_uuid_type1).to_bytes(4, "little")
            + zero_uuid_type1
        )
        assert lc._parse_raw_smbios_uuid(zero_uuid_raw) == ""

        # Clone attack: copying every local licensing file and spoofing the old
        # MachineGuid must not make a newly-issued v2 entitlement valid on
        # different physical hardware.
        clone_guid = "copied-machine-guid"
        source_hardware = "10" * 16
        target_hardware = "20" * 16
        lc._windows_machine_guid = lambda: clone_guid
        lc._windows_smbios_uuid = lambda: source_hardware
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        source_fingerprint = lc.machine_fingerprint()
        assert source_fingerprint == lc._machine_hardware_fingerprint(
            clone_guid,
            source_hardware,
        )
        assert source_fingerprint != lc._machine_guid_fingerprint(clone_guid)
        copied_v2_license = signed_document(private, payload(source_fingerprint))
        source_cache_value, source_cache_requires_hardware = (
            lc._decode_protected_machine_fingerprint_cache_record(
                lc._machine_fingerprint_cache_path().read_text(encoding="utf-8")
            )
        )
        assert source_cache_value == source_fingerprint
        assert source_cache_requires_hardware

        # Keep the source cache files in place: this represents copying the
        # complete installed/runtime folder to the target computer.
        lc._windows_smbios_uuid = lambda: target_hardware
        target_fingerprint = lc.machine_fingerprint()
        assert target_fingerprint == lc._machine_hardware_fingerprint(
            clone_guid,
            target_hardware,
        )
        assert target_fingerprint != source_fingerprint
        try:
            lc._evaluate_document(
                copied_v2_license,
                config,
                allow_uninitialized_clock=True,
            )
            raise AssertionError(
                "copied v2 license survived same-MachineGuid hardware clone"
            )
        except lc.LicenseError:
            pass

        # The stronger cache may never silently downgrade to MachineGuid-only
        # if SMBIOS evidence becomes temporarily unreadable.
        lc._windows_smbios_uuid = lambda: ""
        try:
            lc.machine_fingerprint()
            raise AssertionError("v2 hardware binding silently downgraded")
        except lc.MachineIdentityUnavailableError:
            pass

        # Existing pre-v2 licenses/orders remain compatible. This candidate is
        # accepted only because it is independently derived from the current
        # MachineGuid; new activations use the stronger v2 hash above.
        legacy_guid_fingerprint = lc._machine_guid_fingerprint(clone_guid)
        lc._windows_smbios_uuid = lambda: target_hardware
        assert lc._machine_allowed_by_payload([legacy_guid_fingerprint])
        assert lc.machine_fingerprint() == target_fingerprint
        recovery_candidates = lc._server_machine_hash_candidates()
        assert recovery_candidates[0] == target_fingerprint
        assert legacy_guid_fingerprint in recovery_candidates

        # A paid order created by the previous release must still recover after
        # upgrade: v2 is attempted first, then the exact legacy binding after a
        # server-side 409 machine mismatch. No second payment is created.
        compatibility_document = signed_document(
            private,
            payload(legacy_guid_fingerprint),
        )
        compatibility_calls = []
        old_json_request_for_clone = lc._json_request
        try:
            def _compatibility_request(
                _config,
                method,
                path,
                *,
                body=None,
                bearer="",
            ):
                machine_hash = str((body or {}).get("machine_hash") or "")
                compatibility_calls.append((method, path, machine_hash, bearer))
                if method != "POST":
                    raise AssertionError((method, path))
                if machine_hash == target_fingerprint:
                    raise lc.LicenseError("Сервер лицензий вернул HTTP 409")
                assert machine_hash == legacy_guid_fingerprint
                if path.endswith("/activate-machine"):
                    return {"activated": True, "machine_hash": machine_hash}
                if path.endswith("/license"):
                    return compatibility_document
                raise AssertionError(path)

            lc._json_request = _compatibility_request
            recovered_legacy_document = lc._fetch_paid_order_license(
                config,
                "00000000-0000-0000-0000-000000000077",
                "C" * 48,
                activate=True,
            )
            assert recovered_legacy_document == compatibility_document
            assert compatibility_calls[0][2] == target_fingerprint
            assert any(
                call[2] == legacy_guid_fingerprint
                for call in compatibility_calls
            )
        finally:
            lc._json_request = old_json_request_for_clone

        for path in (lc._clock_path(), lc._clock_backup_path()):
            path.unlink(missing_ok=True)
        lc._windows_smbios_uuid = lambda: ""
        lc._windows_machine_guid = old_guid
        lc._install_id = old_install
        lc._is_windows_runtime = old_windows_runtime
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._cache_machine_fingerprint(machine)

        # Legacy schema-1 fingerprint migration is allowed only when the
        # unprotected value can be independently derived on this machine.
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._windows_machine_guid = lambda: "legacy-guid"
        lc._install_id = lambda: "legacy-install-id"
        legacy_candidates, legacy_guid_available = lc._derived_machine_fingerprint_candidates()
        assert legacy_guid_available
        legacy_local = next(
            value
            for value in legacy_candidates
            if value == __import__("hashlib").sha256(
                b"windows-machine-guid-v1|legacy-guid"
            ).hexdigest()
        )
        lc._machine_fingerprint_cache_path().write_text(
            json.dumps({"schema": 1, "fingerprint": legacy_local}),
            encoding="utf-8",
        )
        assert lc.machine_fingerprint() == legacy_local
        migrated_primary = json.loads(
            lc._machine_fingerprint_cache_path().read_text(encoding="utf-8")
        )
        assert migrated_primary["schema"] == 3

        # A readable MachineGuid is sufficient to validate a legitimate
        # legacy cache even if install-id persistence is temporarily broken.
        old_install_for_failure = lc._install_id
        lc._install_id = lambda: (_ for _ in ()).throw(OSError("read-only LocalAppData"))
        try:
            candidates_without_install, guid_available = lc._derived_machine_fingerprint_candidates()
            assert guid_available
            assert legacy_local in candidates_without_install
        finally:
            lc._install_id = old_install_for_failure

        # A copied/foreign legacy cache must never become the machine identity.
        lc._machine_fingerprint_cache_path().write_text(
            json.dumps({"schema": 1, "fingerprint": "f" * 64}),
            encoding="utf-8",
        )
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        foreign_result = lc.machine_fingerprint()
        assert foreign_result in legacy_candidates
        assert foreign_result != "f" * 64

        # The roaming backup never accepts schema 1. This blocks copying a
        # foreign legacy cache into the newly introduced backup location.
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().write_text(
            json.dumps({"schema": 1, "fingerprint": "e" * 64}),
            encoding="utf-8",
        )
        backup_ignored = lc.machine_fingerprint()
        assert backup_ignored in legacy_candidates
        assert backup_ignored != "e" * 64

        # If a legitimate legacy primary cannot be verified only because
        # MachineGuid is temporarily unreadable, do not overwrite it and do not
        # turn that transient condition into a fresh-payment path.
        lc._machine_fingerprint_cache_path().write_text(
            json.dumps({"schema": 1, "fingerprint": legacy_local}),
            encoding="utf-8",
        )
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._windows_machine_guid = lambda: ""
        lc._install_id = lambda: "different-fallback-id"
        try:
            lc.machine_fingerprint()
            raise AssertionError("unverifiable legacy fingerprint was accepted")
        except lc.MachineIdentityUnavailableError:
            pass
        preserved_legacy = json.loads(
            lc._machine_fingerprint_cache_path().read_text(encoding="utf-8")
        )
        assert preserved_legacy == {"schema": 1, "fingerprint": legacy_local}

        lc._windows_machine_guid = old_guid
        lc._install_id = old_install
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._cache_machine_fingerprint(machine)

        # A legacy schema-2 cache remains readable for compatibility, but a
        # locally forgeable foreign value must not override current Windows
        # MachineGuid evidence even if the attacker can create a valid
        # DPAPI/HMAC envelope containing a copied license fingerprint.
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        old_guid = lc._windows_machine_guid
        old_install = lc._install_id
        old_windows_runtime = lc._is_windows_runtime
        lc._is_windows_runtime = lambda: True
        lc._windows_machine_guid = lambda: "schema2-local-guid"
        lc._install_id = lambda: "attacker-controlled-install-id"
        forged_fingerprint = "d" * 64
        forged_clear = json.dumps(
            {"fingerprint": forged_fingerprint},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        forged_protected = lc._protect_local_blob(
            forged_clear,
            "MedicalDiaryAutofill machine fingerprint",
        )
        forged_cache = json.dumps(
            {"schema": 2, "protected": forged_protected},
            sort_keys=True,
        )
        lc._machine_fingerprint_cache_path().write_text(forged_cache, encoding="utf-8")
        lc._machine_fingerprint_backup_path().write_text(forged_cache, encoding="utf-8")
        expected_local_fingerprint = __import__("hashlib").sha256(
            b"windows-machine-guid-v1|schema2-local-guid"
        ).hexdigest()
        assert lc.machine_fingerprint() == expected_local_fingerprint
        assert lc.machine_fingerprint() != forged_fingerprint
        lc._windows_machine_guid = old_guid
        lc._install_id = old_install
        lc._is_windows_runtime = old_windows_runtime
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._cache_machine_fingerprint(machine)

        # Fingerprint persistence is best-effort resilience. A transient local
        # protection failure must not make machine_fingerprint unusable.
        old_protect_local_blob = lc._protect_local_blob
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._windows_machine_guid = lambda: "stable-guid-for-dpapi-failure"
        try:
            lc._protect_local_blob = lambda *args, **kwargs: (_ for _ in ()).throw(
                lc.LicenseError("simulated DPAPI failure")
            )
            transient_fingerprint = lc.machine_fingerprint()
            assert len(transient_fingerprint) == 64
        finally:
            lc._protect_local_blob = old_protect_local_blob
            lc._windows_machine_guid = old_guid
        lc._cache_machine_fingerprint(machine)

        # Upgrade compatibility with the original production fingerprint
        # (platform|hostname|MachineGuid|install-id). A signed v1 entitlement
        # created by the first licensing release must remain usable on the same
        # Windows machine, while new activations use the strongest available
        # hardware-backed identity.
        saved_windows_runtime = lc._is_windows_runtime
        saved_guid_provider = lc._windows_machine_guid
        saved_hostname_provider = lc.socket.gethostname
        saved_platform_system = lc.platform.system
        saved_json_request = lc._json_request
        install_id_path = lc._install_id_path()
        install_id_existed = install_id_path.exists()
        install_id_before = (
            install_id_path.read_text(encoding="utf-8")
            if install_id_existed
            else ""
        )
        historical_install_id = "1" * 32
        historical_guid = "original-production-guid"
        historical_hostname = "original-production-host"
        try:
            lc._is_windows_runtime = lambda: True
            lc._windows_machine_guid = lambda: historical_guid
            lc.socket.gethostname = lambda: historical_hostname
            lc.platform.system = lambda: "Windows"
            install_id_path.parent.mkdir(parents=True, exist_ok=True)
            install_id_path.write_text(historical_install_id + "\n", encoding="utf-8")
            lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
            lc._machine_fingerprint_backup_path().unlink(missing_ok=True)

            historical_material = "|".join(
                [
                    lc.platform.system().strip().lower(),
                    historical_hostname,
                    historical_guid,
                    historical_install_id,
                ]
            )
            historical_fingerprint = __import__("hashlib").sha256(
                historical_material.encode("utf-8")
            ).hexdigest()
            canonical_fingerprint = lc._machine_guid_fingerprint(historical_guid)
            assert historical_fingerprint != canonical_fingerprint
            assert historical_fingerprint in lc._historical_windows_license_fingerprints()

            # A transient hostname read failure must only disable legacy
            # matching; it may never crash normal licensing/status checks.
            lc.socket.gethostname = lambda: (_ for _ in ()).throw(OSError("hostname unavailable"))
            assert lc._historical_windows_license_fingerprints() == set()
            lc.socket.gethostname = lambda: historical_hostname

            original_release_paid = signed_document(
                private,
                payload(historical_fingerprint, days=31),
                schema=lc.LEGACY_LICENSE_SCHEMA,
            )
            lc.license_path().write_text(
                json.dumps(original_release_paid, ensure_ascii=False),
                encoding="utf-8",
            )
            lc._license_backup_path().unlink(missing_ok=True)
            # The original release used unprotected clock schema 1. It is not
            # trusted directly after the security upgrade; one trusted HTTPS
            # time check migrates it into the protected current clock format.
            lc._clock_path().write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "last_seen_utc": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            lc._clock_backup_path().unlink(missing_ok=True)
            lc._json_request = lambda _config, method, path, **kwargs: (
                {
                    "status": "ok",
                    "product_id": lc.PRODUCT_ID,
                    "public_key_b64": config.public_key_b64,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                }
                if method == "GET" and path == "/health"
                else (_ for _ in ()).throw(AssertionError((method, path)))
            )
            upgraded_original = lc.current_status(config)
            assert upgraded_original.active and upgraded_original.mode == "paid"
            assert json.loads(lc._clock_path().read_text(encoding="utf-8"))["schema"] == 3

            # The first-release unlimited owner entitlement used the same old
            # fingerprint formula. It must remain unlimited on the same machine
            # and must never be routed through monthly-payment clock logic.
            original_release_owner = signed_document(
                private,
                payload(historical_fingerprint, days=3650, owner=True),
                schema=lc.LEGACY_LICENSE_SCHEMA,
            )
            historical_owner_status = lc._evaluate_document(
                original_release_owner,
                config,
            )
            assert historical_owner_status.active
            assert historical_owner_status.mode == "owner"
            assert historical_owner_status.owner_unlimited

            # Historical entitlement matching must never pin the old formula as
            # the identity for future activations.
            assert lc.machine_fingerprint() == canonical_fingerprint
        finally:
            lc._is_windows_runtime = saved_windows_runtime
            lc._windows_machine_guid = saved_guid_provider
            lc.socket.gethostname = saved_hostname_provider
            lc.platform.system = saved_platform_system
            lc._json_request = saved_json_request
            if install_id_existed:
                install_id_path.write_text(install_id_before, encoding="utf-8")
            else:
                install_id_path.unlink(missing_ok=True)
            for path in (
                lc.license_path(),
                lc._license_backup_path(),
                lc._clock_path(),
                lc._clock_backup_path(),
                lc._machine_fingerprint_cache_path(),
                lc._machine_fingerprint_backup_path(),
            ):
                path.unlink(missing_ok=True)

        # Restore the real platform identity functions before the paid-license
        # scenarios. The identity tests above intentionally replace them with
        # failing/forged lambdas; leaking those stubs into the next section
        # would make Windows CI fail for the wrong reason.
        lc._windows_machine_guid = original_windows_machine_guid
        lc._windows_smbios_uuid = original_windows_smbios_uuid
        lc._install_id = original_install_id

        paid = signed_document(private, payload(machine))

        # All paid-license persistence tiers must be independently writable.
        # A LocalAppData failure must still leave a usable Roaming/AppData copy
        # instead of blocking a doctor who has already paid.
        primary_paths = {
            lc.license_path(),
            lc._clock_path(),
            lc._pending_order_path(),
            lc._active_order_path(),
        }
        all_resilience_paths = (
            lc.license_path(),
            lc._license_backup_path(),
            lc._clock_path(),
            lc._clock_backup_path(),
            lc._pending_order_path(),
            lc._pending_order_backup_path(),
            lc._active_order_path(),
            lc._active_order_backup_path(),
        )
        for path in all_resilience_paths:
            path.unlink(missing_ok=True)

        old_atomic_write = lc._atomic_write_text
        def _fail_primary_only(path, text):
            if path in primary_paths:
                raise OSError("simulated LocalAppData write failure")
            return old_atomic_write(path, text)

        resilience_order = {
            "order_id": "00000000-0000-0000-0000-000000000088",
            "order_access_token": "B" * 48,
            "payment_url": "https://pay.example.com/redundant-storage",
            "amount_rub": 100,
        }
        lc._atomic_write_text = _fail_primary_only
        try:
            lc._write_license_document(paid)
            assert not lc.license_path().exists()
            assert lc._license_backup_path().exists()
            assert lc._load_license_document(config) == paid

            clock_now = datetime.now(timezone.utc)
            lc._record_clock(clock_now)
            assert not lc._clock_path().exists()
            assert lc._clock_backup_path().exists()
            assert lc._read_clock_state() is not None

            lc._save_pending_order(resilience_order)
            assert not lc._pending_order_path().exists()
            assert lc._pending_order_backup_path().exists()
            assert lc._load_pending_order()["order_id"] == resilience_order["order_id"]

            lc._save_active_order(resilience_order)
            assert not lc._active_order_path().exists()
            assert lc._active_order_backup_path().exists()
            assert lc._load_active_order()["order_id"] == resilience_order["order_id"]
        finally:
            lc._atomic_write_text = old_atomic_write
            for path in all_resilience_paths:
                path.unlink(missing_ok=True)

        # A partial write can leave both redundant clock files valid but at
        # different generations. The newest monotonic revision must win even
        # when the stale LocalAppData copy contains a later wall-clock value.
        stale_clock_time = datetime.now(timezone.utc) + timedelta(days=3)
        repaired_clock_time = datetime.now(timezone.utc)
        stale_clock_clear = json.dumps(
            {
                "last_seen_utc": stale_clock_time.isoformat(),
                "trusted_offset_seconds": 0,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        repaired_clock_clear = json.dumps(
            {
                "last_seen_utc": repaired_clock_time.isoformat(),
                "trusted_offset_seconds": -300,
                "revision": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        stale_clock_raw = json.dumps(
            {
                "schema": 3,
                "protected": lc._protect_local_blob(
                    stale_clock_clear,
                    "MedicalDiaryAutofill license clock",
                ),
            }
        ) + "\n"
        repaired_clock_raw = json.dumps(
            {
                "schema": 3,
                "protected": lc._protect_local_blob(
                    repaired_clock_clear,
                    "MedicalDiaryAutofill license clock",
                ),
            }
        ) + "\n"
        lc._clock_path().write_text(stale_clock_raw, encoding="utf-8")
        lc._clock_backup_path().write_text(repaired_clock_raw, encoding="utf-8")
        reconciled_clock = lc._read_clock_record()
        assert reconciled_clock is not None
        assert reconciled_clock[0] == repaired_clock_time
        assert reconciled_clock[1] == timedelta(seconds=-300)
        assert reconciled_clock[2] == 1
        assert lc._clock_path().read_text(encoding="utf-8") == repaired_clock_raw
        assert lc._clock_backup_path().read_text(encoding="utf-8") == repaired_clock_raw

        # Legacy schema-2 clock state remains readable after the revision field
        # was added to schema 3.
        legacy_clock_clear = json.dumps(
            {"last_seen_utc": repaired_clock_time.isoformat()},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        legacy_clock_raw = json.dumps(
            {
                "schema": 2,
                "protected": lc._protect_local_blob(
                    legacy_clock_clear,
                    "MedicalDiaryAutofill license clock",
                ),
            }
        )
        legacy_clock_record = lc._decode_clock_record(legacy_clock_raw)
        assert legacy_clock_record == (repaired_clock_time, timedelta(0), 0)

        # The first production client stored pending orders with created_at
        # and no saved_at/backup. Such an unfinished real invoice must survive
        # upgrade and be migrated instead of silently opening a second payment.
        legacy_pending_token = "L" * 48
        legacy_pending_raw = {
            "schema": 1,
            "order_id": "00000000-0000-0000-0000-000000000080",
            "order_access_token": lc._protect_order_token(legacy_pending_token),
            "payment_url": "https://pay.example.com/original-client",
            "amount_rub": 100,
            "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        }
        lc._pending_order_path().write_text(
            json.dumps(legacy_pending_raw, ensure_ascii=False),
            encoding="utf-8",
        )
        lc._pending_order_backup_path().unlink(missing_ok=True)
        migrated_legacy_pending = lc._load_pending_order()
        assert migrated_legacy_pending["order_id"] == legacy_pending_raw["order_id"]
        assert migrated_legacy_pending["order_access_token"] == legacy_pending_token
        assert lc._pending_order_backup_path().exists()
        healed_legacy_pending = lc._load_order_credentials(
            lc._pending_order_backup_path(),
            "missing",
        )
        assert healed_legacy_pending["order_id"] == legacy_pending_raw["order_id"]
        assert healed_legacy_pending.get("saved_at")

        # Pending-payment copies can also diverge if one storage tier rejects a
        # renewal write. Always continue the newest saved invoice; otherwise a
        # stale readable primary could unlock an accidental second payment.
        older_pending = {
            "order_id": "00000000-0000-0000-0000-000000000081",
            "order_access_token": "O" * 48,
            "payment_url": "https://pay.example.com/older",
            "amount_rub": 100,
            "saved_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        }
        newer_pending = {
            "order_id": "00000000-0000-0000-0000-000000000082",
            "order_access_token": "N" * 48,
            "payment_url": "https://pay.example.com/newer",
            "amount_rub": 100,
            "saved_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }
        lc._store_order_credentials(lc._pending_order_path(), older_pending, include_payment=True)
        lc._store_order_credentials(lc._pending_order_backup_path(), newer_pending, include_payment=True)
        loaded_pending = lc._load_pending_order()
        assert loaded_pending["order_id"] == newer_pending["order_id"]
        assert lc._load_order_credentials(
            lc._pending_order_path(),
            "missing",
        )["order_id"] == newer_pending["order_id"]

        # The same newest-copy rule is required for paid recovery credentials.
        older_active = dict(older_pending)
        older_active["order_id"] = "00000000-0000-0000-0000-000000000083"
        newer_active = dict(newer_pending)
        newer_active["order_id"] = "00000000-0000-0000-0000-000000000084"
        lc._store_order_credentials(lc._active_order_path(), older_active, include_payment=False)
        lc._store_order_credentials(lc._active_order_backup_path(), newer_active, include_payment=False)
        loaded_active = lc._load_active_order()
        assert loaded_active["order_id"] == newer_active["order_id"]
        assert lc._load_order_credentials(
            lc._active_order_path(),
            "missing",
        )["order_id"] == newer_active["order_id"]

        for path in (
            lc._pending_order_path(),
            lc._pending_order_backup_path(),
            lc._active_order_path(),
            lc._active_order_backup_path(),
            lc._clock_path(),
            lc._clock_backup_path(),
        ):
            path.unlink(missing_ok=True)

        assert lc.save_license(paid, config).active
        assert lc.current_status(config).mode == "paid"
        assert lc._license_backup_path().exists()

        # A successful renewal may reach only the backup when LocalAppData is
        # temporarily unwritable. A stale but valid signed primary must never
        # hide the newer entitlement or reopen payment UX.
        stale_paid = signed_document(
            private,
            payload(machine, issued_at=datetime.now(timezone.utc) - timedelta(days=60)),
        )
        renewed_paid = signed_document(
            private,
            payload(machine, issued_at=datetime.now(timezone.utc)),
        )
        lc.license_path().write_text(
            json.dumps(stale_paid, ensure_ascii=False),
            encoding="utf-8",
        )
        lc._license_backup_path().write_text(
            json.dumps(renewed_paid, ensure_ascii=False),
            encoding="utf-8",
        )
        reconciled = lc.current_status(config)
        assert reconciled.active and reconciled.mode == "paid"
        assert json.loads(lc.license_path().read_text(encoding="utf-8")) == renewed_paid
        assert json.loads(lc._license_backup_path().read_text(encoding="utf-8")) == renewed_paid

        # A newer roaming copy issued for another computer must never shadow a
        # valid local entitlement merely because its issued_at is later.
        local_paid = signed_document(
            private,
            payload(machine, issued_at=datetime.now(timezone.utc)),
        )
        foreign_machine = "e" * 64
        foreign_newer = signed_document(
            private,
            payload(
                foreign_machine,
                issued_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ),
        )
        lc.license_path().write_text(
            json.dumps(local_paid, ensure_ascii=False),
            encoding="utf-8",
        )
        lc._license_backup_path().write_text(
            json.dumps(foreign_newer, ensure_ascii=False),
            encoding="utf-8",
        )
        local_wins = lc.current_status(config)
        assert local_wins.active and local_wins.mode == "paid"
        assert json.loads(lc.license_path().read_text(encoding="utf-8")) == local_paid
        assert json.loads(lc._license_backup_path().read_text(encoding="utf-8")) == local_paid

        # A cryptographically genuine historical paid entitlement whose signed
        # machine identity no longer matches must never fall through to the
        # "buy again" path. Access still stays closed; only paid recovery is
        # offered. This protects legacy fallback identities across upgrades
        # without weakening current MachineGuid binding.
        for path in (lc._active_order_path(), lc._active_order_backup_path()):
            path.unlink(missing_ok=True)
        legacy_identity_paid = signed_document(
            private,
            payload(foreign_machine, days=31),
            schema=lc.LEGACY_LICENSE_SCHEMA,
        )
        lc.license_path().write_text(
            json.dumps(legacy_identity_paid, ensure_ascii=False),
            encoding="utf-8",
        )
        lc._license_backup_path().write_text(
            json.dumps(legacy_identity_paid, ensure_ascii=False),
            encoding="utf-8",
        )
        old_json_request = lc._json_request
        try:
            lc._json_request = lambda _config, method, path, **kwargs: (
                {
                    "status": "ok",
                    "product_id": lc.PRODUCT_ID,
                    "public_key_b64": config.public_key_b64,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                }
                if method == "GET" and path == "/health"
                else (_ for _ in ()).throw(AssertionError((method, path)))
            )
            legacy_identity_status = lc.current_status(config)
            assert not legacy_identity_status.active
            assert legacy_identity_status.mode == "paid_recovery"
            assert "Новый платёж не нужен" in legacy_identity_status.message

            # The same mismatch must not suppress a legitimate renewal forever
            # after the old signed period has actually expired. Only trusted
            # server time may make this transition into ordinary expired UX.
            expired_legacy_identity = signed_document(
                private,
                payload(
                    foreign_machine,
                    days=31,
                    issued_at=datetime.now(timezone.utc) - timedelta(days=60),
                ),
                schema=lc.LEGACY_LICENSE_SCHEMA,
            )
            lc.license_path().write_text(
                json.dumps(expired_legacy_identity, ensure_ascii=False),
                encoding="utf-8",
            )
            lc._license_backup_path().write_text(
                json.dumps(expired_legacy_identity, ensure_ascii=False),
                encoding="utf-8",
            )
            confirmed_expired = lc.current_status(config)
            assert not confirmed_expired.active
            assert confirmed_expired.mode == "expired"
        finally:
            lc._json_request = old_json_request

        # If trusted server time is unavailable, even an apparently old signed
        # entitlement must stay in paid recovery rather than risking a duplicate
        # charge based only on the workstation clock.
        lc.license_path().write_text(
            json.dumps(legacy_identity_paid, ensure_ascii=False),
            encoding="utf-8",
        )
        lc._license_backup_path().write_text(
            json.dumps(legacy_identity_paid, ensure_ascii=False),
            encoding="utf-8",
        )
        old_json_request = lc._json_request
        try:
            lc._json_request = lambda *args, **kwargs: (_ for _ in ()).throw(
                lc.LicenseError("offline")
            )
            offline_identity_status = lc.current_status(config)
            assert not offline_identity_status.active
            assert offline_identity_status.mode == "paid_recovery"
        finally:
            lc._json_request = old_json_request

        assert lc.save_license(paid, config).active

        # The signed entitlement itself is redundant. Losing the primary copy
        # must heal it from the independent roaming backup without blocking an
        # already-paid doctor.
        lc.license_path().unlink()
        healed_license = lc.current_status(config)
        assert healed_license.active and healed_license.mode == "paid"
        assert lc.license_path().exists()

        # A primary file can remain valid JSON while its signed payload is
        # damaged. Ed25519 failure must make the client fall back to the signed
        # backup rather than treating a paid user as unlicensed.
        tampered_primary = json.loads(lc.license_path().read_text(encoding="utf-8"))
        tampered_primary["license"]["payload"]["document_limit_month"] = 999999
        lc.license_path().write_text(
            json.dumps(tampered_primary, ensure_ascii=False),
            encoding="utf-8",
        )
        healed_license = lc.current_status(config)
        assert healed_license.active and healed_license.mode == "paid"
        assert json.loads(lc.license_path().read_text(encoding="utf-8")) == paid

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

            # Once payment is confirmed, a transient failure while promoting
            # the order token into long-lived recovery storage must not block
            # the signed license itself. Keep the pending token instead.
            local_storage_order = {
                "order_id": "00000000-0000-0000-0000-000000000010",
                "order_access_token": "V" * 48,
                "payment_url": "https://pay.example.com/local-storage",
                "amount_rub": 100,
            }
            lc._save_pending_order(local_storage_order)
            old_save_active = lc._save_active_order
            try:
                lc._save_active_order = lambda _order: (_ for _ in ()).throw(
                    lc.LicenseError("simulated DPAPI failure")
                )

                def _storage_request(_config, method, path, *, body=None, bearer=""):
                    if method == "GET" and path.endswith("/status"):
                        return {
                            "status": "paid",
                            "amount_rub": 100,
                            "server_time": paid["license"]["payload"]["issued_at"],
                        }
                    if method == "POST" and path.endswith("/activate-machine"):
                        return {"activated": True, "machine_hash": machine}
                    if method == "POST" and path.endswith("/license"):
                        return paid
                    raise AssertionError((method, path, body, bearer))

                lc._json_request = _storage_request
                storage_status = lc.refresh_paid_order(config)
                assert storage_status.active and storage_status.mode == "paid"
                assert lc.pending_payment_details()["order_id"] == local_storage_order["order_id"]
            finally:
                lc._save_active_order = old_save_active
                lc._json_request = _paid_request
            lc.discard_pending_order()

            active_primary = lc._active_order_path().read_text(encoding="utf-8")
            lc._active_order_path().unlink()
            backup_loaded = lc._load_active_order()
            assert backup_loaded["order_id"] == recovery_order["order_id"]
            lc._active_order_path().write_text("{broken", encoding="utf-8")
            backup_loaded = lc._load_active_order()
            assert backup_loaded["order_id"] == recovery_order["order_id"]
            lc._active_order_path().write_text(active_primary, encoding="utf-8")

            # One damaged license/clock primary copy must heal from the
            # independent signed/protected backups with no user-visible block.
            lc.license_path().write_text("{broken", encoding="utf-8")
            lc._clock_path().write_text("{broken", encoding="utf-8")
            automatically_healed = lc.current_status(config)
            assert automatically_healed.active
            assert automatically_healed.mode == "paid"

            # If both signed license copies are damaged, the already-saved
            # active order credential becomes the next recovery tier.
            lc.license_path().write_text("{broken", encoding="utf-8")
            lc._license_backup_path().write_text("{broken", encoding="utf-8")
            lc._clock_path().write_text("{broken", encoding="utf-8")
            lc._clock_backup_path().write_text("{broken", encoding="utf-8")
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
        expired_text = json.dumps(expired_document, ensure_ascii=False)
        lc.license_path().write_text(expired_text, encoding="utf-8")
        lc._license_backup_path().write_text(expired_text, encoding="utf-8")
        lc._clock_path().unlink(missing_ok=True)
        lc._record_clock(datetime.now(timezone.utc))
        expired_local = lc.current_status(config)
        assert not expired_local.active
        assert expired_local.mode == "paid_recovery"

        # Observing a cryptographically valid expired license must advance the
        # protected rollback state. Rolling Windows time back into the old paid
        # period must not resurrect the entitlement.
        guard_now = datetime.now(timezone.utc)
        rollback_payload = payload(
            machine,
            issued_at=guard_now - timedelta(days=60),
        )
        rollback_document = signed_document(private, rollback_payload)
        lc._clock_path().unlink(missing_ok=True)
        lc._clock_backup_path().unlink(missing_ok=True)
        expired_guard = lc._evaluate_document(
            rollback_document,
            config,
            now=guard_now,
            allow_uninitialized_clock=True,
        )
        assert not expired_guard.active and expired_guard.mode == "expired"
        recorded_expiry = lc._read_clock_state()
        assert recorded_expiry is not None
        assert abs((recorded_expiry - guard_now).total_seconds()) < 1
        try:
            lc._evaluate_document(
                rollback_document,
                config,
                now=guard_now - timedelta(days=45),
            )
            raise AssertionError("clock rollback resurrected an expired paid license")
        except lc.LicenseError as exc:
            assert "rollback" in str(exc)

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
            stored_clock = json.loads(lc._clock_path().read_text(encoding="utf-8"))
            assert stored_clock["schema"] == 3

            # The successful server-time check must establish a durable trusted
            # time basis. A paid user with a badly wrong Windows clock must not
            # require the server again on every launch.
            lc._json_request = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("trusted-time activation required another online check")
            )
            offline_after_trusted_time = lc.current_status(config)
            assert offline_after_trusted_time.active
            assert offline_after_trusted_time.mode == "paid"
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
        assert lc._owner_marker_local_path().exists()
        assert lc._owner_marker_path().exists()

        owner_marker_local = lc._owner_marker_local_path().read_text(encoding="utf-8")
        owner_marker_roaming = lc._owner_marker_path().read_text(encoding="utf-8")
        lc._owner_marker_local_path().unlink()
        assert lc._has_owner_marker()
        lc._owner_marker_local_path().write_text(owner_marker_local, encoding="utf-8")
        lc._owner_marker_path().unlink()
        assert lc._has_owner_marker()
        lc._owner_marker_path().write_text(owner_marker_roaming, encoding="utf-8")

        # Owner-marker persistence is redundant too. If LocalAppData is
        # temporarily unwritable, the Roaming/AppData copy alone must preserve
        # owner-only reactivation semantics instead of ever exposing payment.
        old_atomic_write = lc._atomic_write_text
        lc._owner_marker_local_path().unlink(missing_ok=True)
        lc._owner_marker_path().unlink(missing_ok=True)
        try:
            def _fail_local_owner_marker(path, text):
                if path == lc._owner_marker_local_path():
                    raise OSError("simulated LocalAppData owner-marker failure")
                return old_atomic_write(path, text)

            lc._atomic_write_text = _fail_local_owner_marker
            lc._write_owner_marker()
            assert not lc._owner_marker_local_path().exists()
            assert lc._owner_marker_path().exists()
            assert lc._has_owner_marker()
        finally:
            lc._atomic_write_text = old_atomic_write
            lc._owner_marker_local_path().write_text(owner_marker_local, encoding="utf-8")
            lc._owner_marker_path().write_text(owner_marker_roaming, encoding="utf-8")

        # The owner marker never grants access by itself. It only forces
        # owner-only reactivation if both signed license copies are lost or damaged.
        owner_license_text = lc.license_path().read_text(encoding="utf-8")
        owner_backup_text = lc._license_backup_path().read_text(encoding="utf-8")

        # Losing only the primary signed license must heal transparently from
        # the independent signed backup and keep owner access active.
        lc.license_path().unlink()
        healed_owner = lc.current_status(config)
        assert healed_owner.active
        assert healed_owner.mode == "owner"
        assert healed_owner.owner_unlimited
        assert lc.license_path().exists()

        # Owner reactivation is required only when both signed copies are gone
        # (or both are unusable); it must never be confused with paid renewal.
        lc.license_path().unlink(missing_ok=True)
        lc._license_backup_path().unlink(missing_ok=True)
        lost_owner = lc.current_status(config)
        assert not lost_owner.active
        assert lost_owner.mode == "owner_reactivation"
        assert lost_owner.owner_unlimited

        lc.license_path().write_text("{broken", encoding="utf-8")
        lc._license_backup_path().write_text("{broken", encoding="utf-8")
        damaged_owner = lc.current_status(config)
        assert not damaged_owner.active
        assert damaged_owner.mode == "owner_reactivation"
        assert damaged_owner.owner_unlimited

        lc.license_path().write_text(owner_license_text, encoding="utf-8")
        lc._license_backup_path().write_text(owner_backup_text, encoding="utf-8")

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
        # Simulate the authoritative Windows identity source itself, not only
        # machine_fingerprint(), because redundant-copy selection deliberately
        # re-derives MachineGuid evidence independently.
        old_guid_provider = lc._windows_machine_guid
        lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
        lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
        lc._windows_machine_guid = lambda: "owner-moved-to-another-machine"
        try:
            reactivation = lc.current_status(config)
            assert not reactivation.active
            assert reactivation.mode == "owner_reactivation"
            assert reactivation.owner_unlimited
        finally:
            lc._windows_machine_guid = old_guid_provider
            lc._machine_fingerprint_cache_path().unlink(missing_ok=True)
            lc._machine_fingerprint_backup_path().unlink(missing_ok=True)
            lc._cache_machine_fingerprint(machine)

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
        assert "license-backup.json" not in installer_text
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
