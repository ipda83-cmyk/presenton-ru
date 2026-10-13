"""YooKassa API v3 (https://yookassa.ru/developers/api): payments with a redirect,
payments with a saved card (auto top-up), payment lookup.

Every payment carries a 54-FZ receipt: one "service" item, full payment, VAT code
from the settings (1 = no VAT). The tax system code is not sent: with a single
tax system "Чеки от ЮKassa" rejects it (checked by the standalone Studio).
"""

import base64
import logging
from typing import Any, Callable, Optional
import uuid

import aiohttp

from services.billing import settings

LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)


class YooKassaError(Exception):
    def __init__(self, detail: str, status: Optional[int] = None):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def receipt(amount: int, description: str, email: str) -> dict:
    return {
        "customer": {"email": email},
        "items": [
            {
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                "vat_code": settings.vat_code(),
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }
        ],
    }


class YooKassa:
    def __init__(
        self,
        shop_id: str,
        secret_key: str,
        base_url: str,
        *,
        session_factory: Callable[..., Any] = aiohttp.ClientSession,
    ):
        self.base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode()
        self._auth = f"Basic {token}"
        self._session_factory = session_factory

    async def _request(self, method: str, path: str, body: Optional[dict] = None, idempotence_key: Optional[str] = None) -> dict:
        headers = {"Authorization": self._auth, "Content-Type": "application/json"}
        if method == "POST":
            headers["Idempotence-Key"] = idempotence_key or str(uuid.uuid4())
        try:
            async with self._session_factory(timeout=TIMEOUT) as session:
                async with session.request(method, f"{self.base_url}{path}", json=body, headers=headers) as response:
                    payload = await response.json(content_type=None)
                    status = response.status
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            LOGGER.warning("YooKassa %s %s failed: %r", method, path, error)
            raise YooKassaError("unavailable") from error
        if status >= 400 or not isinstance(payload, dict):
            detail = payload.get("description") if isinstance(payload, dict) else None
            LOGGER.warning("YooKassa %s %s -> %s %s", method, path, status, payload)
            raise YooKassaError(str(detail or f"HTTP {status}")[:300], status)
        return payload

    async def create_payment(
        self,
        *,
        amount: int,
        description: str,
        return_url: str,
        email: str,
        metadata: dict[str, str],
        save_method: bool,
        idempotence_key: str,
    ) -> dict:
        body = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:128],
            "metadata": metadata,
            "receipt": receipt(amount, description, email),
        }
        if save_method:
            body["save_payment_method"] = True
        return await self._request("POST", "/payments", body, idempotence_key)

    async def charge_saved(
        self,
        *,
        amount: int,
        method_id: str,
        description: str,
        email: str,
        metadata: dict[str, str],
        idempotence_key: str,
    ) -> dict:
        body = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "capture": True,
            "payment_method_id": method_id,
            "description": description[:128],
            "metadata": metadata,
            "receipt": receipt(amount, description, email),
        }
        return await self._request("POST", "/payments", body, idempotence_key)

    async def get_payment(self, payment_id: str) -> dict:
        safe = "".join(ch for ch in payment_id if ch.isalnum() or ch == "-")[:64]
        if not safe:
            raise YooKassaError("bad payment id")
        return await self._request("GET", f"/payments/{safe}")


def client() -> Optional[YooKassa]:
    credentials = settings.yookassa_credentials()
    if credentials is None:
        return None
    return YooKassa(*credentials, settings.yookassa_api_url())
