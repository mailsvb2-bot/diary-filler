"""Current product policy: licensing code stays intact but is disabled for users."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def _assert_implementation_is_preserved() -> None:
    required = (
        ROOT / "license_client.py",
        ROOT / "license_ui.py",
        ROOT / "licensing_server" / "core.py",
        ROOT / "licensing_server" / "store.py",
        ROOT / "licensing_server" / "app.py",
        ROOT / "tests" / "license_client_regression.py",
        ROOT / "tests" / "license_server_regression.py",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, "licensing implementation was removed: " + ", ".join(missing)

    client = (ROOT / "license_client.py").read_text(encoding="utf-8")
    ui = (ROOT / "license_ui.py").read_text(encoding="utf-8")
    for marker in (
        "def runtime_config()",
        "def activate_owner(",
        "def begin_monthly_payment(",
        "def recover_paid_license(",
        "def current_status(",
    ):
        assert marker in client, marker
    for marker in (
        "def show_license_manager(",
        "def ensure_license(",
        "def ensure_generation_license(",
    ):
        assert marker in ui, marker


def _assert_current_release_policy_is_unlicensed() -> None:
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    for marker in (
        'MEDICAL_AUTOFILL_RELEASE_LICENSE_MODE: "unlicensed"',
        'MEDICAL_AUTOFILL_LICENSE_REQUIRED: "0"',
        'MEDICAL_AUTOFILL_LICENSE_SERVER_URL: ""',
        'MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64: ""',
        "Temporary release policy verified: licensing is disabled in this binary.",
    ):
        assert marker in release, marker

    renderer = (ROOT / "tools" / "render_license_build_config.py").read_text(encoding="utf-8")
    assert 'policy_mode == "unlicensed"' in renderer
    assert "unlicensed release policy requires LICENSE_REQUIRED=0 and empty server/key" in renderer

    client = (ROOT / "license_client.py").read_text(encoding="utf-8")
    assert 'if embedded_policy == "unlicensed":' in client
    assert "server_url = """ in client
    assert "public_key_b64 = """ in client
    assert "required = False" in client


def _assert_unlicensed_runtime_cannot_be_resurrected_by_environment() -> None:
    with TemporaryDirectory(prefix="license-off-contract-") as temp:
        generated = Path(temp) / "license_build_config.py"
        generated.write_text(
            "LICENSE_SERVER_URL = ''\n"
            "LICENSE_PUBLIC_KEY_B64 = ''\n"
            "LICENSE_REQUIRED = False\n"
            "LICENSE_POLICY_MODE = 'unlicensed'\n",
            encoding="utf-8",
        )

        import sys
        sys.path.insert(0, temp)
        saved = {
            name: os.environ.get(name)
            for name in (
                "MEDICAL_AUTOFILL_LICENSE_SERVER_URL",
                "MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64",
                "MEDICAL_AUTOFILL_LICENSE_REQUIRED",
            )
        }
        try:
            # Even hostile/stale machine-wide variables must not turn licensing
            # back on in a binary explicitly built with unlicensed policy.
            os.environ["MEDICAL_AUTOFILL_LICENSE_SERVER_URL"] = "https://example.invalid"
            os.environ["MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64"] = "ZmFrZQ=="
            os.environ["MEDICAL_AUTOFILL_LICENSE_REQUIRED"] = "1"

            import license_client
            importlib.reload(license_client)
            config = license_client.runtime_config()
            assert config.required is False
            assert config.server_url == ""
            assert config.public_key_b64 == ""
        finally:
            sys.path.remove(temp)
            sys.modules.pop("license_build_config", None)
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def _assert_disabled_mode_never_blocks_user_paths() -> None:
    ui = (ROOT / "license_ui.py").read_text(encoding="utf-8")
    assert "if not config.required:\n        return True" in ui
    assert "if not config.required:\n        return" in ui

    main = (ROOT / "main.py").read_text(encoding="utf-8")
    orchestrator = (ROOT / "actions_creation_orchestrator.py").read_text(encoding="utf-8")
    forbidden = (
        "ensure_license(",
        "ensure_generation_license(",
        "show_license_manager(",
    )
    for marker in forbidden:
        assert marker not in main, f"startup is license-gated by {marker}"
        assert marker not in orchestrator, f"document generation is license-gated by {marker}"


def main() -> None:
    _assert_implementation_is_preserved()
    _assert_current_release_policy_is_unlicensed()
    _assert_unlicensed_runtime_cannot_be_resurrected_by_environment()
    _assert_disabled_mode_never_blocks_user_paths()
    print(
        "LICENSING DISABLED-MODE CONTRACT OK: full licensing implementation is preserved, "
        "current release embeds immutable unlicensed policy, and startup/generation remain unrestricted"
    )


if __name__ == "__main__":
    main()
