"""Durable SQLite persistence for the MedicalDiaryAutofill license service."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Iterator


class LicenseStore:
    def __init__(self, path: str | Path, *, backup_path: str | Path | None = None):
        self.path = Path(path)
        self.backup_path = Path(backup_path) if backup_path is not None else None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.backup_path is not None:
            self.backup_path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.resolve() == self.backup_path.resolve():
                raise ValueError("license database backup path must differ from primary path")
        self._durability_lock = threading.Lock()
        self._last_backup_error: str | None = None
        self._restored_from_backup = False
        self._bootstrap_storage()

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

    @staticmethod
    def _quick_check(path: Path) -> tuple[bool, str]:
        if not path.is_file():
            return False, "missing"
        try:
            con = sqlite3.connect(str(path), timeout=10)
            try:
                con.execute("PRAGMA query_only=ON")
                row = con.execute("PRAGMA quick_check").fetchone()
            finally:
                con.close()
        except (OSError, sqlite3.Error) as exc:
            return False, exc.__class__.__name__
        if not row or str(row[0]).lower() != "ok":
            return False, str(row[0] if row else "quick_check_failed")
        return True, "ok"

    @staticmethod
    def _copy_database(source_path: Path, destination_path: Path) -> None:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temp = destination_path.with_name(
            destination_path.name + f".tmp-{os.getpid()}-{threading.get_ident()}"
        )
        try:
            temp.unlink(missing_ok=True)
            source = sqlite3.connect(str(source_path), timeout=15)
            destination = sqlite3.connect(str(temp), timeout=15)
            try:
                source.backup(destination)
                row = destination.execute("PRAGMA quick_check").fetchone()
                if not row or str(row[0]).lower() != "ok":
                    raise sqlite3.DatabaseError(
                        f"backup quick_check failed: {row[0] if row else 'missing result'}"
                    )
            finally:
                destination.close()
                source.close()
            os.replace(temp, destination_path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

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

    def _bootstrap_storage(self) -> None:
        primary_exists = self.path.exists()
        primary_ok, primary_reason = self._quick_check(self.path)
        backup_exists = self.backup_path is not None and self.backup_path.exists()
        if self.backup_path is not None:
            backup_ok, backup_reason = self._quick_check(self.backup_path)
        else:
            backup_ok, backup_reason = False, "not_configured"

        if primary_ok:
            self._init_schema()
            if self.backup_path is not None:
                # Primary is authoritative when healthy. Rebuild a missing or
                # damaged backup immediately before accepting traffic.
                self._snapshot_backup_required()
            return

        if self.backup_path is not None and backup_ok:
            # Restore a missing/corrupt primary from the last consistent online
            # SQLite backup, then reopen normally in WAL mode.
            self._copy_database(self.backup_path, self.path)
            restored_ok, restored_reason = self._quick_check(self.path)
            if not restored_ok:
                raise RuntimeError(
                    f"restored license database failed integrity check: {restored_reason}"
                )
            self._restored_from_backup = True
            self._init_schema()
            self._snapshot_backup_required()
            return

        if primary_exists or backup_exists:
            raise RuntimeError(
                "license database durability failure: "
                f"primary={primary_reason}, backup={backup_reason}"
            )

        # Brand-new deployment. Create schema, then require the first durable
        # snapshot before the server can start accepting payment traffic.
        self._init_schema()
        if self.backup_path is not None:
            self._snapshot_backup_required()

    def _snapshot_backup_required(self) -> None:
        if self.backup_path is None:
            return
        with self._durability_lock:
            self._copy_database(self.path, self.backup_path)
            ok, reason = self._quick_check(self.backup_path)
            if not ok:
                raise RuntimeError(f"license database backup failed integrity check: {reason}")
            self._last_backup_error = None

    def _snapshot_backup_best_effort(self) -> None:
        if self.backup_path is None:
            return
        try:
            self._snapshot_backup_required()
        except Exception as exc:
            # A backup-volume outage must not turn a successful payment/license
            # operation into a user-visible failure or provoke another charge.
            # Health becomes degraded until a later snapshot succeeds.
            self._last_backup_error = exc.__class__.__name__

    def durability_status(self) -> dict:
        primary_ok, _primary_reason = self._quick_check(self.path)
        if self.backup_path is None:
            backup_ok = False
        else:
            backup_ok, _backup_reason = self._quick_check(self.backup_path)
        healthy = (
            primary_ok
            and self.backup_path is not None
            and backup_ok
            and self._last_backup_error is None
        )
        return {
            "status": "ok" if healthy else "degraded",
            "backup_configured": self.backup_path is not None,
            "primary_integrity": "ok" if primary_ok else "failed",
            "backup_integrity": "ok" if backup_ok else "failed",
            "restored_from_backup": self._restored_from_backup,
        }

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
            elif str(row["value"]) != value:
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
                else:
                    con.execute("ROLLBACK")
                    raise ValueError(
                        "issuer public key changed after paid licenses already exist"
                    )
            else:
                con.execute("COMMIT")
        self._snapshot_backup_best_effort()

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
        self._snapshot_backup_best_effort()

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
        self._snapshot_backup_best_effort()

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
        self._snapshot_backup_best_effort()

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
            elif row["status"] != "paid":
                con.execute("ROLLBACK")
                raise ValueError("order is not paid")
            else:
                con.execute(
                    """
                    UPDATE license_orders
                       SET license_json = ?, status = 'license_issued'
                     WHERE order_id = ?
                    """,
                    (encoded, order_id),
                )
                con.execute("COMMIT")
        self._snapshot_backup_best_effort()

    def load_license(self, order_id: str) -> dict | None:
        row = self.get_order(order_id)
        if not row or not row.get("license_json"):
            return None
        return json.loads(row["license_json"])
