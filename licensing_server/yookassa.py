"""Minimal YooKassa API client with server-side payment verification."""
from __future__ import annotations

import base64
import json
from decimal import Decimal
import urllib.error
import urllib.request


class YooKassaError(RuntimeError):
    pass


class YooKassaClient:
    API = "https://api.yookassa.ru/v3"

    def __init__(self, shop_id: str, secret_key: str, return_url: str):
        self.shop_id = shop_id.strip()
        self.secret_key = secret_key.strip()
        self.return_url = return_url.strip()
        if not self.shop_id or not self.secret_key or not self.return_url.startswith("https://"):
            raise YooKassaError("YooKassa production configuration is incomplete")

    def _request(self, method: str, path: str, *, body: dict | None = None, idempotence_key: str = "") -> dict:
        token = base64.b64encode(f"{self.shop_id}:{self.secret_key}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": "Basic " + token,
            "Accept": "application/json",
            "User-Agent": "MedicalDiaryAutofill-LicenseServer/1",
        }
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotence_key:
            headers["Idempotence-Key"] = idempotence_key
        request = urllib.request.Request(self.API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read(512 * 1024)
        except urllib.error.HTTPError as exc:
            raise YooKassaError(f"YooKassa HTTP {exc.code}") from exc
        except OSError as exc:
            raise YooKassaError("YooKassa is unavailable") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise YooKassaError("YooKassa returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise YooKassaError("YooKassa returned an invalid response")
        return payload

    def create_payment(self, *, order_id: str, amount_rub: int, description: str) -> dict:
        body = {
            "amount": {"value": f"{int(amount_rub)}.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": self.return_url},
            "description": description[:128],
            "metadata": {"order_id": order_id, "product_id": "diary_filler"},
        }
        payload = self._request("POST", "/payments", body=body, idempotence_key=order_id)
        confirmation = payload.get("confirmation") or {}
        payment_id = str(payload.get("id") or "")
        payment_url = str(confirmation.get("confirmation_url") or "")
        if not payment_id or not payment_url:
            raise YooKassaError("YooKassa did not return payment id/url")
        return {"payment_id": payment_id, "payment_url": payment_url}

    def get_payment(self, payment_id: str) -> dict:
        return self._request("GET", f"/payments/{payment_id}")

    @staticmethod
    def payment_matches_order(payment: dict, *, order_id: str, amount_rub: int) -> bool:
        metadata = payment.get("metadata") or {}
        amount = payment.get("amount") or {}
        try:
            provider_amount = Decimal(str(amount.get("value") or ""))
        except Exception:
            return False
        return (
            str(metadata.get("order_id") or "") == order_id
            and str(metadata.get("product_id") or "") == "diary_filler"
            and str(amount.get("currency") or "") == "RUB"
            and provider_amount == Decimal(int(amount_rub))
        )
