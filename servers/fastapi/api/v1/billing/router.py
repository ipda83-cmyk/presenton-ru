"""Balance, top-ups and auto top-up for signed-in users; YooKassa webhook (public)."""

import re
import uuid
from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.v1.auth.context import get_current_owner_id, get_current_owner_is_admin
from models.sql.billing import BillingAccount
from models.sql.user import User
from services.billing import ledger, payments, settings
from services.billing.pricing import price_table
from services.billing.yookassa import client
from services.database import async_session_maker
from utils.get_env import get_presenton_public_url
from utils.i18n import http_error

API_V1_BILLING_ROUTER = APIRouter(prefix="/api/v1/billing", tags=["Billing"])
API_V1_ADMIN_BILLING_ROUTER = APIRouter(prefix="/api/v1/admin/billing", tags=["Billing"])
WEBHOOK_PATH = "/api/v1/billing/yookassa/webhook"

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,63}$")


def _owner() -> uuid.UUID:
    owner = get_current_owner_id()
    if owner is None or not settings.billing_enabled():
        raise http_error(404, "err.billing.disabled")
    return owner


def public_base_url(request: Request) -> str:
    configured = get_presenton_public_url()
    if configured:
        return configured
    proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
    scheme = proto if proto in ("http", "https") else request.url.scheme
    host = (request.headers.get("x-forwarded-host") or "").split(",", 1)[0].strip()
    return f"{scheme}://{host or request.headers.get('host') or request.url.netloc}"


@API_V1_BILLING_ROUTER.get("/me")
async def billing_me():
    owner = get_current_owner_id()
    base = {
        "prices": price_table(),
        "topup_amounts": list(settings.TOPUP_AMOUNTS),
        "payments_available": client() is not None,
        "offer_url": settings.offer_url(),
        "signup_bonus": settings.signup_bonus(),
    }
    if owner is None or not settings.billing_enabled():
        return {"enabled": False, "free": True, **base}
    await payments.refresh_pending(owner)
    async with async_session_maker() as session:
        account = await ledger._account(session, owner)
    return {"enabled": True, "free": get_current_owner_is_admin(), **base, **payments.account_dict(account)}


@API_V1_BILLING_ROUTER.get("/history")
async def billing_history(limit: int = Query(default=50, ge=1, le=200)):
    owner = _owner()
    return {
        "entries": [ledger.entry_dict(entry) for entry in await ledger.history(owner, limit)],
        "payments": [payments.payment_dict(payment) for payment in await payments.recent_payments(owner)],
    }


class TopupRequest(BaseModel):
    amount: int
    email: str = Field(default="", max_length=254)
    save_card: bool = False
    consent: bool = False


@API_V1_BILLING_ROUTER.post("/topup")
async def billing_topup(body: TopupRequest, request: Request):
    owner = _owner()
    if body.amount not in settings.TOPUP_AMOUNTS:
        raise http_error(400, "err.billing.badAmount")
    email = body.email.strip()
    if not EMAIL.match(email):
        raise http_error(400, "err.billing.emailRequired")
    if body.save_card and not body.consent:
        raise http_error(400, "err.billing.consentRequired")
    try:
        return await payments.create_topup(
            owner,
            body.amount,
            email=email,
            save_card=body.save_card,
            return_url=f"{public_base_url(request)}/billing?payment=",
        )
    except payments.PaymentsUnavailable:
        raise http_error(503, "err.billing.paymentsUnavailable")
    except payments.TopupRejected as error:
        raise http_error(502, "err.billing.paymentFailed", detail=error.detail)


@API_V1_BILLING_ROUTER.post("/payments/{invoice_id}/check")
async def billing_check_payment(invoice_id: str):
    owner = _owner()
    payment = await payments.check_payment(owner, invoice_id[:64])
    if payment is None:
        raise http_error(404, "err.billing.paymentNotFound")
    return {**payments.payment_dict(payment), "balance": await ledger.balance_of(owner)}


class AutoTopupRequest(BaseModel):
    enabled: bool
    threshold: int = Field(ge=settings.AUTO_TOPUP_THRESHOLD_RANGE[0], le=settings.AUTO_TOPUP_THRESHOLD_RANGE[1])
    amount: int = Field(ge=settings.AUTO_TOPUP_AMOUNT_RANGE[0], le=settings.AUTO_TOPUP_AMOUNT_RANGE[1])


@API_V1_BILLING_ROUTER.put("/auto-topup")
async def billing_auto_topup(body: AutoTopupRequest):
    owner = _owner()
    async with async_session_maker() as session:
        account = await ledger._account(session, owner)
    if body.enabled and not account.saved_method_id:
        raise http_error(400, "err.billing.cardRequired")
    account = await payments.set_auto_topup(owner, enabled=body.enabled, threshold=body.threshold, amount=body.amount)
    return payments.account_dict(account)


@API_V1_BILLING_ROUTER.delete("/card", status_code=204)
async def billing_forget_card():
    await payments.forget_card(_owner())
    return Response(status_code=204)


@API_V1_BILLING_ROUTER.post("/yookassa/webhook")
async def yookassa_webhook(request: Request):
    """YooKassa notifications. The body is only a hint: the payment is looked up
    at YooKassa before anything is credited. Always 200 for well-formed calls so
    YooKassa does not retry forever on our side's trouble."""
    try:
        body = await request.json()
    except ValueError:
        return Response(status_code=400)
    payment_id = ((body or {}).get("object") or {}).get("id") if isinstance(body, dict) else None
    if isinstance(payment_id, str) and payment_id:
        await payments.verify(payment_id)
    return {"ok": True}


# ---------------------------------------------------------------- administrators


@API_V1_ADMIN_BILLING_ROUTER.get("/accounts")
async def admin_billing_accounts():
    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(User.id, User.username, User.is_superuser, BillingAccount)
                .outerjoin(BillingAccount, BillingAccount.user_id == User.id)
                .order_by(User.username)
            )
        ).all()
    return {
        "accounts": [
            {
                "user_id": str(user_id),
                "username": username,
                "admin": bool(is_admin),
                "balance": account.balance if account else None,
                "card": bool(account and account.saved_method_id),
                "auto_topup": bool(account and account.auto_topup_enabled),
            }
            for user_id, username, is_admin, account in rows
        ],
        "signup_bonus": settings.signup_bonus(),
    }


class AdjustRequest(BaseModel):
    user_id: uuid.UUID
    amount: int = Field(ge=-1_000_000, le=1_000_000)
    mode: Literal["add", "set"] = "add"
    note: str = Field(default="", max_length=200)


@API_V1_ADMIN_BILLING_ROUTER.post("/adjust")
async def admin_billing_adjust(body: AdjustRequest):
    async with async_session_maker() as session:
        if await session.get(User, body.user_id) is None:
            raise http_error(404, "err.billing.userNotFound")
    balance = await ledger.admin_adjust(
        body.user_id, body.amount, mode=body.mode, admin_id=get_current_owner_id(), note=body.note
    )
    return {"user_id": str(body.user_id), "balance": balance}


@API_V1_ADMIN_BILLING_ROUTER.get("/history/{user_id}")
async def admin_billing_history(user_id: uuid.UUID, limit: int = Query(default=100, ge=1, le=500)):
    async with async_session_maker() as session:
        if await session.get(User, user_id) is None:
            raise http_error(404, "err.billing.userNotFound")
    return {
        "entries": [ledger.entry_dict(entry) for entry in await ledger.history(user_id, limit)],
        "payments": [payments.payment_dict(payment) for payment in await payments.recent_payments(user_id, 50)],
    }
