"""Generate an Ed25519 key pair for the diary-filler licensing server."""
from __future__ import annotations

import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    print("DIARY_FILLER_LICENSE_PRIVATE_KEY_B64=" + base64.b64encode(private_raw).decode("ascii"))
    print("MEDICAL_AUTOFILL_LICENSE_PUBLIC_KEY_B64=" + base64.b64encode(public_raw).decode("ascii"))


if __name__ == "__main__":
    main()
