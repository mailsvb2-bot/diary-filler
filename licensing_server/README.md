# MedicalDiaryAutofill licensing server

This service is part of the `diary-filler` repository. It handles monthly
YooKassa payments and issues Ed25519-signed licenses consumed by
`license_client.py`.

Required environment:

- `DIARY_FILLER_MONTHLY_PRICE_RUB` — monthly price in RUB; intentionally has no default.
- `DIARY_FILLER_LICENSE_PRIVATE_KEY_B64` — raw 32-byte Ed25519 private key in base64.
- `DIARY_FILLER_LICENSE_DB` — SQLite path (optional; defaults under the service account home).
- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `DIARY_FILLER_PAYMENT_RETURN_URL` — HTTPS return URL, normally `https://<host>/payment-return`.

Run behind HTTPS/reverse proxy:

```bash
python -m pip install -r licensing_server/requirements.txt
uvicorn licensing_server.app:app --host 127.0.0.1 --port 8787
```

Configure YooKassa to send notifications to
`https://<host>/api/webhooks/yookassa`. The webhook does **not** trust the
incoming status: it fetches the payment from YooKassa again and verifies order
metadata, product id, currency and amount before marking an order paid.

The owner bootstrap code is represented only by a fixed scrypt digest in
`licensing_server/core.py`; its plaintext is not committed. Owner issuance is
separately rate-limited and produces a machine-bound, Ed25519-signed
`owner_superadmin` license with `access=unlimited`.
