"""FastAPI service for MedicalDiaryAutofill monthly licenses."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .core import (
    LicensingServerError,
    issue_license,
    new_order_access_token,
    order_token_hash,
    order_token_matches,
    owner_code_matches,
    public_key_b64,
    validate_machine_hash,
)
from .store import LicenseStore
from .yookassa import YooKassaClient, YooKassaError


class OrderRequest(BaseModel):
    plan: str = "doctor_start"
    machine_hash: str


class MachineRequest(BaseModel):
    machine_hash: str


class OwnerRequest(BaseModel):
    bootstrap_code: str
    machine_hash: str


class SlidingLimiter:
    def __init__(self, limit: int, window: timedelta):
        self.limit = limit
        self.window = window
        self._events: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - self.window
        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def _config() -> dict:
    price_raw = os.environ.get("DIARY_FILLER_MONTHLY_PRICE_RUB", "").strip()
    try:
        price = int(price_raw)
    except ValueError as exc:
        raise RuntimeError("DIARY_FILLER_MONTHLY_PRICE_RUB must be a positive integer") from exc
    if price <= 0:
        raise RuntimeError("DIARY_FILLER_MONTHLY_PRICE_RUB must be a positive integer")
    private_key = os.environ.get("DIARY_FILLER_LICENSE_PRIVATE_KEY_B64", "").strip()
    if not private_key:
        raise RuntimeError("DIARY_FILLER_LICENSE_PRIVATE_KEY_B64 is required")
    db_path = os.environ.get(
        "DIARY_FILLER_LICENSE_DB",
        str(Path.home() / ".medical-diary-license-server" / "licenses.sqlite3"),
    )
    return {
        "price": price,
        "private_key": private_key,
        "db_path": db_path,
        "shop_id": os.environ.get("YOOKASSA_SHOP_ID", ""),
        "secret_key": os.environ.get("YOOKASSA_SECRET_KEY", ""),
        "return_url": os.environ.get("DIARY_FILLER_PAYMENT_RETURN_URL", ""),
    }


def create_app() -> FastAPI:
    config = _config()
    store = LicenseStore(config["db_path"])
    provider = YooKassaClient(config["shop_id"], config["secret_key"], config["return_url"])
    owner_limiter = SlidingLimiter(10, timedelta(hours=1))
    order_limiter = SlidingLimiter(30, timedelta(hours=1))

    app = FastAPI(title="MedicalDiaryAutofill License Server", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.provider = provider
    app.state.config = config
    app.state.owner_limiter = owner_limiter
    app.state.order_limiter = order_limiter

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def authorized_order(order_id: str, authorization: str | None) -> dict:
        row = store.get_order(order_id)
        if row is None:
            raise HTTPException(401, "unauthorized")
        prefix = "Bearer "
        if not authorization or not authorization.startswith(prefix):
            raise HTTPException(401, "unauthorized")
        if not order_token_matches(authorization[len(prefix):], row["token_hash"]):
            raise HTTPException(401, "unauthorized")
        return row

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "product_id": "diary_filler", "public_key_b64": public_key_b64(config["private_key"])}

    @app.get("/payment-return", response_class=HTMLResponse)
    def payment_return() -> str:
        return "<h2>Оплата принята к проверке</h2><p>Вернитесь в MedicalDiaryAutofill и нажмите ОК.</p>"

    @app.post("/api/orders")
    def create_order(req: OrderRequest, request: Request) -> dict:
        if req.plan != "doctor_start":
            raise HTTPException(400, "unsupported plan")
        try:
            machine = validate_machine_hash(req.machine_hash)
        except LicensingServerError as exc:
            raise HTTPException(400, str(exc)) from exc
        # Include the machine identity in the bucket. Behind a reverse proxy
        # many legitimate doctors may share request.client.host; they must not
        # collectively consume one 30-order allowance.
        if not order_limiter.allow(f"{client_ip(request)}|{machine}"):
            raise HTTPException(429, "too many orders")
        order_id = str(uuid.uuid4())
        access_token = new_order_access_token()
        try:
            payment = provider.create_payment(
                order_id=order_id,
                amount_rub=config["price"],
                description="MedicalDiaryAutofill — лицензия на 1 месяц",
            )
        except YooKassaError as exc:
            raise HTTPException(503, str(exc)) from exc
        store.create_order(
            order_id=order_id,
            token_hash=order_token_hash(access_token),
            machine_hash=machine,
            amount_rub=config["price"],
            provider_payment_id=payment["payment_id"],
            payment_url=payment["payment_url"],
        )
        return {
            "order_id": order_id,
            "order_access_token": access_token,
            "payment_url": payment["payment_url"],
            "amount_rub": config["price"],
            "status": "pending",
        }

    def reconcile_payment(row: dict) -> dict:
        if row["status"] not in {"pending", "created"}:
            return row
        try:
            payment = provider.get_payment(str(row["provider_payment_id"]))
        except YooKassaError:
            return row
        if not provider.payment_matches_order(
            payment,
            order_id=row["order_id"],
            amount_rub=row["amount_rub"],
        ):
            return row
        status = str(payment.get("status") or "").lower()
        paid = bool(payment.get("paid"))
        if status == "succeeded" and paid:
            store.mark_paid(row["order_id"])
        elif status == "canceled":
            store.mark_cancelled(row["order_id"])
        return store.get_order(row["order_id"]) or row

    @app.get("/api/orders/{order_id}/status")
    def order_status(order_id: str, authorization: str | None = Header(default=None)) -> dict:
        row = authorized_order(order_id, authorization)
        row = reconcile_payment(row)
        return {
            "order_id": order_id,
            "status": row["status"],
            "amount_rub": row["amount_rub"],
            "server_time": datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/api/orders/{order_id}/activate-machine")
    def activate_machine(order_id: str, req: MachineRequest, authorization: str | None = Header(default=None)) -> dict:
        row = authorized_order(order_id, authorization)
        try:
            machine = validate_machine_hash(req.machine_hash)
        except LicensingServerError as exc:
            raise HTTPException(400, str(exc)) from exc
        if row["status"] not in {"paid", "license_issued"}:
            raise HTTPException(409, "order is not paid")
        if machine != row["machine_hash"]:
            raise HTTPException(409, "order belongs to another computer")
        return {"activated": True, "machine_hash": machine}

    @app.post("/api/orders/{order_id}/license")
    def order_license(order_id: str, req: MachineRequest, authorization: str | None = Header(default=None)) -> dict:
        row = authorized_order(order_id, authorization)
        try:
            machine = validate_machine_hash(req.machine_hash)
        except LicensingServerError as exc:
            raise HTTPException(400, str(exc)) from exc
        if machine != row["machine_hash"]:
            raise HTTPException(409, "order belongs to another computer")
        existing = store.load_license(order_id)
        if existing is not None:
            return existing
        if row["status"] != "paid":
            raise HTTPException(409, "order is not paid")
        document = issue_license(
            config["private_key"],
            machine_hash=machine,
            order_id=order_id,
            owner=False,
        )
        store.save_license(order_id, document)
        return document

    @app.post("/api/owner/license")
    def owner_license(req: OwnerRequest, request: Request) -> dict:
        if not owner_limiter.allow(client_ip(request)):
            raise HTTPException(429, "too many owner attempts")
        try:
            machine = validate_machine_hash(req.machine_hash)
        except LicensingServerError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not owner_code_matches(req.bootstrap_code):
            raise HTTPException(401, "invalid owner code")
        return issue_license(
            config["private_key"],
            machine_hash=machine,
            order_id=None,
            owner=True,
        )

    @app.post("/api/webhooks/yookassa")
    async def yookassa_webhook(request: Request) -> dict:
        try:
            event = await request.json()
        except Exception as exc:
            raise HTTPException(400, "invalid webhook JSON") from exc
        payment_id = str(((event or {}).get("object") or {}).get("id") or "")
        if not payment_id:
            raise HTTPException(400, "missing payment id")
        row = store.get_order_by_payment(payment_id)
        if row is None:
            raise HTTPException(404, "unknown payment")
        try:
            payment = provider.get_payment(payment_id)
        except YooKassaError as exc:
            raise HTTPException(503, str(exc)) from exc
        if not provider.payment_matches_order(
            payment,
            order_id=row["order_id"],
            amount_rub=row["amount_rub"],
        ):
            raise HTTPException(409, "payment/order mismatch")
        status = str(payment.get("status") or "").lower()
        paid = bool(payment.get("paid"))
        if status == "succeeded" and paid:
            store.mark_paid(row["order_id"])
        elif status == "canceled":
            store.mark_cancelled(row["order_id"])
        return {"ok": True}

    return app


app = create_app()
