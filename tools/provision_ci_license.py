"""Provision a real signed license for licensed GitHub Actions E2E.

This is not a licensing bypass. It calls the same HTTPS activation endpoint as
the application and stores the server-signed entitlement in the selected
APPDATA/LOCALAPPDATA profile. The activation code is accepted only from the
GitHub Actions environment and is never printed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import license_client as lc


MARKER_NAME = "ci-license-provisioned.marker"


def _require_github_actions() -> None:
    if os.environ.get("GITHUB_ACTIONS", "").strip().lower() != "true":
        raise SystemExit("CI license provisioning is allowed only in GitHub Actions")


def _marker_path() -> Path:
    return lc._runtime_dir() / MARKER_NAME


def _managed_paths() -> tuple[Path, ...]:
    return (
        lc.license_path(),
        lc._license_backup_path(),
        lc._clock_path(),
        lc._clock_backup_path(),
        lc._owner_marker_local_path(),
        lc._owner_marker_path(),
        lc._machine_fingerprint_cache_path(),
        lc._machine_fingerprint_backup_path(),
        lc._pending_order_path(),
        lc._pending_order_backup_path(),
        lc._active_order_path(),
        lc._active_order_backup_path(),
        lc._install_id_path(),
    )


def _config() -> lc.LicenseRuntimeConfig:
    server_url = os.environ.get("MEDICAL_AUTOFILL_LICENSE_SERVER_URL", "").strip().rstrip("/")
    public_key = os.environ.get("MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64", "").strip()
    if not server_url or not public_key:
        raise SystemExit("production license server URL/public key are required for licensed E2E")
    return lc.LicenseRuntimeConfig(
        server_url=server_url,
        public_key_b64=public_key,
        required=True,
    )


def provision() -> None:
    _require_github_actions()
    if os.environ.get("MEDICAL_AUTOFILL_LICENSE_REQUIRED", "").strip() != "1":
        raise SystemExit("licensed E2E provisioning requires MEDICAL_AUTOFILL_LICENSE_REQUIRED=1")

    marker = _marker_path()
    preexisting = [str(path) for path in _managed_paths() if path.exists()]
    if marker.exists() or preexisting:
        raise SystemExit(
            "refusing to overwrite pre-existing license state in the CI profile"
        )

    code = os.environ.get("MEDICAL_AUTOFILL_CI_ACTIVATION_CODE", "").strip()
    if not code:
        raise SystemExit(
            "MEDICAL_AUTOFILL_CI_ACTIVATION_CODE GitHub Actions secret is required"
        )

    status = lc.activate_owner(code, _config())
    if not status.active or not status.owner_unlimited:
        raise SystemExit("CI activation did not return an active signed entitlement")

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("github-actions-signed-license\n", encoding="utf-8")
    verified = lc.current_status(_config())
    if not verified.active:
        raise SystemExit("provisioned CI entitlement did not survive a normal status check")
    print("LICENSED E2E PROFILE PROVISIONED")


def cleanup() -> None:
    _require_github_actions()
    marker = _marker_path()
    if not marker.is_file():
        return
    for path in (*_managed_paths(), marker):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    print("LICENSED E2E PROFILE CLEANED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        cleanup()
    else:
        provision()


if __name__ == "__main__":
    main()
