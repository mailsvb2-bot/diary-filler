"""SQLite persistence for the MedicalDiaryAutofill license service."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Iterator


class LicenseStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            yield con
        finally:
            con.close()

    def _init_schema(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS license_orders (
                    order_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    machine_hash TEXT NOT NULL,
                    amount_rub INTEGER NOT NULL CHECK(amount_rub > 0),
                    status TEXT NOT NULL,
                    provider_payment_id TEXT UNIQUE,
                    payment_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    paid_at TEXT,
                    license_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_license_orders_payment
                    ON license_orders(provider_payment_id);
                CREATE TABLE IF NOT EXISTS license_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def pin_issuer_public_key(self, public_key_b64: str) -> None:
        value = str(public_key_b64 or "").strip()
        if not value:
            raise ValueError("issuer public key is empty")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT value FROM license_meta WHERE key = 'issuer_public_key_b64'"
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO license_meta(key, value) VALUES('issuer_public_key_b64', ?)",
                    (value,),
                )
                con.execute("COMMIT")
                return
            if str(row["value"]) != value:
                protected = con.execute(
                    """
                    SELECT COUNT(*) AS count
                      FROM license_orders
                     WHERE status IN ('paid', 'license_issued')
                        OR license_json IS NOT NULL
                    """
                ).fetchone()
                if int(protected["count"] or 0) == 0:
                    con.execute(
                        "UPDATE license_meta SET value = ? WHERE key = 'issuer_public_key_b64'",
                        (value,),
                    )
                    con.execute("COMMIT")
                    return
                con.execute("ROLLBACK")
                raise ValueError(
                    "issuer public key changed after paid licenses already exist"
                )
            con.execute("COMMIT")

    def create_order(
        self,
        *,
        order_id: str,
        token_hash: str,
        machine_hash: str,
        amount_rub: int,
        provider_payment_id: str,
        payment_url: str,
    ) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO license_orders(
                    order_id, token_hash, machine_hash, amount_rub, status,
                    provider_payment_id, payment_url, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    order_id,
                    token_hash,
                    machine_hash,
                    int(amount_rub),
                    provider_payment_id,
                    payment_url,
                    self._now(),
                ),
            )

    def get_order(self, order_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM license_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_order_by_payment(self, payment_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM license_orders WHERE provider_payment_id = ?",
                (payment_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark_paid(self, order_id: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                UPDATE license_orders
                   SET status = CASE WHEN status = 'license_issued' THEN status ELSE 'paid' END,
                       paid_at = COALESCE(paid_at, ?)
                 WHERE order_id = ?
                """,
                (self._now(), order_id),
            )

    def mark_cancelled(self, order_id: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                UPDATE license_orders
                   SET status = CASE WHEN status = 'license_issued' THEN status ELSE 'cancelled' END
                 WHERE order_id = ?
                """,
                (order_id,),
            )

    def save_license(self, order_id: str, document: dict) -> None:
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT status, license_json FROM license_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if row is None:
                con.execute("ROLLBACK")
                raise KeyError(order_id)
            if row["license_json"]:
                con.execute("COMMIT")
                return
            if row["status"] != "paid":
                con.execute("ROLLBACK")
                raise ValueError("order is not paid")
            con.execute(
                """
                UPDATE license_orders
                   SET license_json = ?, status = 'license_issued'
                 WHERE order_id = ?
                """,
                (encoded, order_id),
            )
            con.execute("COMMIT")

    def load_license(self, order_id: str) -> dict | None:
        row = self.get_order(order_id)
        if not row or not row.get("license_json"):
            return None
        return json.loads(row["license_json"])
