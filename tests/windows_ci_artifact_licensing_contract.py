"""Lock Windows CI binary publication to production licensing configuration."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-build.yml"

CONDITION = "if: ${{ vars.MEDICAL_AUTOFILL_LICENSE_SERVER_URL != '' && vars.MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64 != '' }}"


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
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

    print("WINDOWS BINARY LICENSING CONTRACT OK")


if __name__ == "__main__":
    main()
