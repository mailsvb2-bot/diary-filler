"""Lock licensed Windows artifacts to real signed-license E2E."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-build.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
DESKTOP_E2E = ROOT / "tools" / "windows_desktop_intake_e2e.ps1"
INSTALLER_SMOKE = ROOT / "tools" / "windows_installer_smoke.ps1"
CI_LICENSE_PROVISIONER = ROOT / "tools" / "provision_ci_license.py"

CONDITION = "if: ${{ vars.MEDICAL_AUTOFILL_LICENSE_SERVER_URL != '' && vars.MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64 != '' }}"
CI_ACTIVATION_BINDING = (
    "MEDICAL_AUTOFILL_CI_ACTIVATION_CODE: "
    "${{ secrets.MEDICAL_AUTOFILL_CI_ACTIVATION_CODE }}"
)


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    desktop = DESKTOP_E2E.read_text(encoding="utf-8")
    installer_smoke = INSTALLER_SMOKE.read_text(encoding="utf-8")
    provisioner = CI_LICENSE_PROVISIONER.read_text(encoding="utf-8")

    required = (
        "Guard binary artifact licensing policy",
        "MEDICAL_AUTOFILL_LICENSE_SERVER_URL: ${{ vars.MEDICAL_AUTOFILL_LICENSE_SERVER_URL }}",
        "MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64: ${{ vars.MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64 }}",
        "MEDICAL_AUTOFILL_LICENSE_REQUIRED:",
        "License variables are absent: binary artifacts will NOT be published.",
        "Upload EXE artifact",
        "Upload Windows installer artifact",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(
            "WINDOWS BINARY LICENSING CONTRACT FAILED: missing " + ", ".join(missing)
        )

    if text.count(CONDITION) != 2:
        raise SystemExit(
            "WINDOWS BINARY LICENSING CONTRACT FAILED: "
            "EXE and installer uploads must both, and only both, use the production licensing condition"
        )

    exe = text.index("      - name: Upload EXE artifact")
    installer = text.index("      - name: Upload Windows installer artifact")
    source = text.index("      - name: Upload source release artifact")
    for start, end, label in (
        (exe, installer, "EXE"),
        (installer, source, "installer"),
    ):
        block = text[start:end]
        if CONDITION not in block:
            raise SystemExit(
                f"WINDOWS BINARY LICENSING CONTRACT FAILED: {label} upload is not license-gated"
            )

    source_block = text[source:]
    if CONDITION in source_block:
        raise SystemExit(
            "WINDOWS BINARY LICENSING CONTRACT FAILED: source archive must remain available independently"
        )

    for workflow_text, label in ((text, "Windows CI"), (release, "release")):
        if workflow_text.count(CI_ACTIVATION_BINDING) != 2:
            raise SystemExit(
                f"WINDOWS BINARY LICENSING CONTRACT FAILED: {label} must scope the "
                "CI activation secret to packaged and installer E2E only"
            )

    for script_text, label in (
        (desktop, "packaged desktop E2E"),
        (installer_smoke, "installer smoke"),
    ):
        for required_item in (
            "provision_ci_license.py",
            "MEDICAL_AUTOFILL_LICENSE_REQUIRED",
            "MEDICAL_AUTOFILL_CI_ACTIVATION_CODE",
        ):
            if required_item not in script_text:
                raise SystemExit(
                    f"WINDOWS BINARY LICENSING CONTRACT FAILED: {label} missing {required_item}"
                )

    if "Remove('MEDICAL_AUTOFILL_CI_ACTIVATION_CODE')" not in desktop:
        raise SystemExit(
            "WINDOWS BINARY LICENSING CONTRACT FAILED: packaged app may inherit the CI activation secret"
        )
    if "Remove-Item Env:MEDICAL_AUTOFILL_CI_ACTIVATION_CODE" not in installer_smoke:
        raise SystemExit(
            "WINDOWS BINARY LICENSING CONTRACT FAILED: installed app may inherit the CI activation secret"
        )

    for required_item in (
        'os.environ.get("GITHUB_ACTIONS"',
        "lc.activate_owner(",
        "lc.current_status(",
        "refusing to overwrite pre-existing license state",
    ):
        if required_item not in provisioner:
            raise SystemExit(
                "WINDOWS BINARY LICENSING CONTRACT FAILED: signed CI provisioner missing "
                + required_item
            )
    for forbidden in ("required=False", "LicenseStatus(True"):
        if forbidden in provisioner:
            raise SystemExit(
                "WINDOWS BINARY LICENSING CONTRACT FAILED: CI provisioner contains bypass marker "
                + forbidden
            )

    print(
        "WINDOWS BINARY LICENSING CONTRACT OK: published licensed binaries are "
        "tested with real server-signed entitlements and no bypass"
    )


if __name__ == "__main__":
    main()
