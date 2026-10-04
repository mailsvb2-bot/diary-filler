# MedicalDiaryAutofill licensing server

This service is part of the `diary-filler` repository. It handles monthly
YooKassa payments and issues Ed25519-signed licenses consumed by
`license_client.py`.

Required environment:

- `DIARY_FILLER_MONTHLY_PRICE_RUB` — monthly price in RUB; intentionally has no default.
- `DIARY_FILLER_LICENSE_PRIVATE_KEY_B64` — raw 32-byte Ed25519 private key in base64.
- `DIARY_FILLER_LICENSE_DB` — primary SQLite path (optional; defaults under the service account home).
- `DIARY_FILLER_LICENSE_BACKUP_DB` — **required** secondary SQLite backup path. Put it on a different persistent volume/storage target from the primary database; using another filename on the same ephemeral disk does not protect paid users from disk loss.
- `YOOKASSA_SHOP_ID`
- `YOOKASSA_SECRET_KEY`
- `DIARY_FILLER_PAYMENT_RETURN_URL` — HTTPS return URL, normally `https://<host>/payment-return`.

Run behind HTTPS/reverse proxy:

```bash
python -m pip install -r licensing_server/requirements.txt
uvicorn licensing_server.app:app --host 127.0.0.1 --port 8787 --workers 1
```

Configure YooKassa to send notifications to
`https://<host>/api/webhooks/yookassa`. The webhook does **not** trust the
incoming status: it fetches the payment from YooKassa again and verifies order
metadata, product id, currency and amount before marking an order paid.

The owner bootstrap code is represented only by a fixed scrypt digest in
`licensing_server/core.py`; its plaintext is not committed. Owner issuance is
separately rate-limited and produces a machine-bound, Ed25519-signed
`owner_superadmin` license with `access=unlimited`.


## Paid-order durability

The server uses SQLite online backup to keep a transactionally consistent
secondary copy of the order/license database. Every mutation attempts to
refresh the secondary copy. A temporary backup-volume outage does **not** turn
an already successful payment or license transition into a client error; the
primary remains authoritative and `/health` reports `degraded` until a later
snapshot succeeds.

On startup:

- healthy primary + missing/corrupt backup -> backup is rebuilt from primary;
- missing/corrupt primary + healthy backup -> primary is restored automatically;
- both copies corrupt -> startup fails closed instead of silently starting with
  an empty database and forgetting paid users.

While durability is degraded the server refuses **new** payment-order creation
before contacting YooKassa, but continues serving existing paid/license-issued
orders from the healthy primary database.

Run one application worker. The in-process snapshot lock assumes a single
license-server process; scale the HTTP edge/reverse proxy, not SQLite writers.

The official release preflight requires `/health` to report healthy primary
and backup integrity before a production client release can be published.
