"""Top-ups through YooKassa: a payment page, then the money lands on the balance.

A payment is credited only after YooKassa itself confirms it (`GET /payments/{id}`):
the webhook body and the user's return are just hints to look. Crediting is
idempotent (pending -> completed in one UPDATE) and checks the amount.

Auto top-up (offer 3.1.3, 3.1.7): when the balance falls below the user's
threshold, the saved card is charged, at most once an hour; after 3 failed
attempts in a row auto top-up switches off.
"""

import asyncio
from datetime import timedelta
import logging
import secrets
import time
from typing import Optional
import uuid

from sqlalchemy import select, update

from models.sql.billing import BillingAccount, BillingPayment
from services.billing import ledger, settings
from services.billing.yookassa import YooKassaError, client
from services.database import async_session_maker
from utils.datetime_utils import get_current_utc_datetime

LOGGER = logging.getLogger(__name__)

AUTO_TOPUP_INTERVAL = timedelta(hours=1)
AUTO_TOPUP_MAX_FAILURES = 3
PENDING_RECHECK_WINDOW = timedelta(days=2)
DESCRIPTION = "Пополнение баланса Kvant AI Studio на {amount} ₽"
AUTO_DESCRIPTION = "Автопополнение баланса Kvant AI Studio на {amount} ₽"
_background: set[asyncio.Task] = set()


class PaymentsUnavailable(Exception):
    pass


class TopupRejected(Exception):
    """The provider refused to create the payment; `detail` is safe to show."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def _invoice(prefix: str) -> str:
    return f"{prefix}-{int(time.time())}-{secrets.token_hex(4)}"


def payment_dict(payment: BillingPayment) -> dict:
    return {
        "invoice_id": payment.invoice_id,
        "amount": payment.amount,
        "kind": payment.kind,
        "status": payment.status,
        "created_at": payment.created_at,
    }


async def create_topup(user_id: uuid.UUID, amount: int, *, email: str, save_card: bool, return_url: str) -> dict:
    yookassa = client()
    if yookassa is None:
        raise PaymentsUnavailable()
    invoice_id = _invoice("TOP")
    async with async_session_maker() as session:
        await ledger._account(session, user_id)
        await session.execute(
            update(BillingAccount)
            .where(BillingAccount.user_id == user_id)
            .values(receipt_email=email, updated_at=get_current_utc_datetime())
        )
        session.add(BillingPayment(user_id=user_id, invoice_id=invoice_id, amount=amount, kind="topup", save_card=save_card))
        await session.commit()
    try:
        created = await yookassa.create_payment(
            amount=amount,
            description=DESCRIPTION.format(amount=amount),
            return_url=f"{return_url}{invoice_id}",
            email=email,
            metadata={"invoice_id": invoice_id, "user_id": str(user_id), "kind": "topup"},
            save_method=save_card,
            idempotence_key=invoice_id,
        )
    except YooKassaError as error:
        await _set_status(invoice_id, "failed")
        if error.status is None or error.status >= 500:
            raise PaymentsUnavailable() from error
        raise TopupRejected(error.detail) from error
    confirmation = (created.get("confirmation") or {}).get("confirmation_url")
    async with async_session_maker() as session:
        await session.execute(
            update(BillingPayment)
            .where(BillingPayment.invoice_id == invoice_id)
            .values(provider_payment_id=str(created.get("id") or "")[:64] or None, updated_at=get_current_utc_datetime())
        )
        await session.commit()
    if not confirmation:
        await _set_status(invoice_id, "failed")
        raise TopupRejected("no confirmation url")
    return {"invoice_id": invoice_id, "confirmation_url": confirmation}


async def _set_status(invoice_id: str, status: str) -> None:
    async with async_session_maker() as session:
        await session.execute(
            update(BillingPayment)
            .where(BillingPayment.invoice_id == invoice_id, BillingPayment.status == "pending")
            .values(status=status, updated_at=get_current_utc_datetime())
        )
        await session.commit()


def _amount_rub(payload: dict) -> Optional[int]:
    amount = payload.get("amount") or {}
    if amount.get("currency") != "RUB":
        return None
    try:
        value = float(amount.get("value"))
    except (TypeError, ValueError):
        return None
    return int(value) if value.is_integer() else None


async def apply_provider_state(provider: dict) -> Optional[str]:
    """Bring our payment in line with a payment object fetched from YooKassa.
    Returns our status, or None when the payment is not ours."""
    metadata = provider.get("metadata") or {}
    invoice_id = str(metadata.get("invoice_id") or "")
    if not invoice_id:
        return None
    async with async_session_maker() as session:
        payment = await session.scalar(select(BillingPayment).where(BillingPayment.invoice_id == invoice_id))
        if payment is None:
            return None
        if payment.provider_payment_id and provider.get("id") != payment.provider_payment_id:
            LOGGER.warning("YooKassa payment %s does not match invoice %s", provider.get("id"), invoice_id)
            return payment.status
        state = provider.get("status")
        if state == "canceled":
            await session.execute(
                update(BillingPayment)
                .where(BillingPayment.id == payment.id, BillingPayment.status == "pending")
                .values(status="failed", updated_at=get_current_utc_datetime())
            )
            await session.commit()
            return "failed" if payment.status == "pending" else payment.status
        if state != "succeeded" or not provider.get("paid", True):
            return payment.status
        if _amount_rub(provider) != payment.amount or metadata.get("user_id") not in (None, str(payment.user_id)):
            LOGGER.error("YooKassa payment %s amount/user mismatch for %s", provider.get("id"), invoice_id)
            return payment.status
        await ledger._account(session, payment.user_id)
        claimed = await session.execute(
            update(BillingPayment)
            .where(BillingPayment.id == payment.id, BillingPayment.status.in_(("pending", "failed")))
            .values(status="completed", provider_payment_id=str(provider.get("id"))[:64], updated_at=get_current_utc_datetime())
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            await session.rollback()
            return "completed"
        await ledger.apply_change(
            session,
            payment.user_id,
            payment.amount,
            kind="auto_topup" if payment.kind == "auto_topup" else "topup",
            reason="yookassa",
            reference=invoice_id,
            idempotency_key=f"payment:{invoice_id}",
        )
        method = provider.get("payment_method") or {}
        if payment.save_card and method.get("saved") and method.get("id"):
            card = method.get("card") or {}
            await session.execute(
                update(BillingAccount)
                .where(BillingAccount.user_id == payment.user_id)
                .values(
                    saved_method_id=str(method["id"])[:128],
                    card_last4=str(card.get("last4") or "")[:4] or None,
                    card_type=str(card.get("card_type") or "")[:32] or None,
                    updated_at=get_current_utc_datetime(),
                )
            )
        await session.commit()
        LOGGER.info("Payment %s: %s RUB credited to %s", invoice_id, payment.amount, payment.user_id)
        return "completed"


async def verify(provider_payment_id: str) -> Optional[str]:
    """Look the payment up at YooKassa and apply what it says."""
    yookassa = client()
    if yookassa is None or not provider_payment_id:
        return None
    try:
        provider = await yookassa.get_payment(provider_payment_id)
    except YooKassaError:
        return None
    return await apply_provider_state(provider)


async def check_payment(user_id: uuid.UUID, invoice_id: str) -> Optional[BillingPayment]:
    """The user is back from the payment page (works without a public webhook)."""
    async with async_session_maker() as session:
        payment = await session.scalar(
            select(BillingPayment).where(BillingPayment.invoice_id == invoice_id, BillingPayment.user_id == user_id)
        )
    if payment is None:
        return None
    if payment.status == "pending" and payment.provider_payment_id:
        await verify(payment.provider_payment_id)
        async with async_session_maker() as session:
            payment = await session.get(BillingPayment, payment.id)
    return payment


async def refresh_pending(user_id: uuid.UUID, limit: int = 3) -> None:
    """Re-check a few recent pending payments (a missed webhook, a closed tab)."""
    async with async_session_maker() as session:
        pending = (
            await session.scalars(
                select(BillingPayment)
                .where(
                    BillingPayment.user_id == user_id,
                    BillingPayment.status == "pending",
                    BillingPayment.provider_payment_id.is_not(None),
                    BillingPayment.created_at > get_current_utc_datetime() - PENDING_RECHECK_WINDOW,
                )
                .order_by(BillingPayment.created_at.desc())
                .limit(limit)
            )
        ).all()
    for payment in pending:
        await verify(payment.provider_payment_id)


async def recent_payments(user_id: uuid.UUID, limit: int = 20) -> list[BillingPayment]:
    async with async_session_maker() as session:
        return list(
            await session.scalars(
                select(BillingPayment)
                .where(BillingPayment.user_id == user_id)
                .order_by(BillingPayment.created_at.desc())
                .limit(limit)
            )
        )


# ---------------------------------------------------------------- auto top-up


def schedule_auto_topup(user_id: Optional[uuid.UUID]) -> None:
    """After a charge: top the balance up in the background if the user asked for it."""
    if user_id is None or client() is None:
        return
    task = asyncio.create_task(_auto_topup_quietly(user_id))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _auto_topup_quietly(user_id: uuid.UUID) -> None:
    try:
        await maybe_auto_topup(user_id)
    except Exception:  # never break the request that triggered it
        LOGGER.exception("Auto top-up failed for %s", user_id)


async def maybe_auto_topup(user_id: uuid.UUID) -> Optional[str]:
    yookassa = client()
    if yookassa is None:
        return None
    now = get_current_utc_datetime()
    async with async_session_maker() as session:
        # Claiming the attempt time first: parallel charges start one top-up, not several.
        claimed = await session.execute(
            update(BillingAccount)
            .where(
                BillingAccount.user_id == user_id,
                BillingAccount.auto_topup_enabled == True,  # noqa: E712
                BillingAccount.saved_method_id.is_not(None),
                BillingAccount.balance < BillingAccount.auto_topup_threshold,
                (BillingAccount.last_auto_topup_at.is_(None)) | (BillingAccount.last_auto_topup_at < now - AUTO_TOPUP_INTERVAL),
            )
            .values(last_auto_topup_at=now)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            await session.rollback()
            return None
        account = await session.get(BillingAccount, user_id, populate_existing=True)
        amount = account.auto_topup_amount
        invoice_id = _invoice("AUTO")
        session.add(BillingPayment(user_id=user_id, invoice_id=invoice_id, amount=amount, kind="auto_topup"))
        await session.commit()
    try:
        provider = await yookassa.charge_saved(
            amount=amount,
            method_id=account.saved_method_id,
            description=AUTO_DESCRIPTION.format(amount=amount),
            email=account.receipt_email or "",
            metadata={"invoice_id": invoice_id, "user_id": str(user_id), "kind": "auto_topup"},
            idempotence_key=invoice_id,
        )
    except YooKassaError:
        await _set_status(invoice_id, "failed")
        await _switch_off_after_failures(user_id)
        return "failed"
    async with async_session_maker() as session:
        await session.execute(
            update(BillingPayment)
            .where(BillingPayment.invoice_id == invoice_id)
            .values(provider_payment_id=str(provider.get("id") or "")[:64] or None)
        )
        await session.commit()
    status = await apply_provider_state(provider)
    if status == "failed":
        await _switch_off_after_failures(user_id)
    return status


async def _switch_off_after_failures(user_id: uuid.UUID) -> None:
    async with async_session_maker() as session:
        recent = (
            await session.scalars(
                select(BillingPayment.status)
                .where(BillingPayment.user_id == user_id, BillingPayment.kind == "auto_topup")
                .order_by(BillingPayment.created_at.desc())
                .limit(AUTO_TOPUP_MAX_FAILURES)
            )
        ).all()
        if len(recent) >= AUTO_TOPUP_MAX_FAILURES and all(status == "failed" for status in recent):
            await session.execute(
                update(BillingAccount).where(BillingAccount.user_id == user_id).values(auto_topup_enabled=False)
            )
            await session.commit()
            LOGGER.warning("Auto top-up switched off for %s after %s failures", user_id, AUTO_TOPUP_MAX_FAILURES)


async def set_auto_topup(user_id: uuid.UUID, *, enabled: bool, threshold: int, amount: int) -> BillingAccount:
    async with async_session_maker() as session:
        account = await ledger._account(session, user_id)
        account.auto_topup_enabled = bool(enabled and account.saved_method_id)
        account.auto_topup_threshold = threshold
        account.auto_topup_amount = amount
        account.updated_at = get_current_utc_datetime()
        session.add(account)
        await session.commit()
        return account


async def forget_card(user_id: uuid.UUID) -> None:
    async with async_session_maker() as session:
        await ledger._account(session, user_id)
        await session.execute(
            update(BillingAccount)
            .where(BillingAccount.user_id == user_id)
            .values(saved_method_id=None, card_last4=None, card_type=None, auto_topup_enabled=False, updated_at=get_current_utc_datetime())
        )
        await session.commit()


def account_dict(account: BillingAccount) -> dict:
    return {
        "balance": account.balance,
        "receipt_email": account.receipt_email,
        "card": (
            {"last4": account.card_last4, "type": account.card_type}
            if account.saved_method_id
            else None
        ),
        "auto_topup": {
            "enabled": account.auto_topup_enabled,
            "threshold": account.auto_topup_threshold,
            "amount": account.auto_topup_amount,
            "threshold_range": list(settings.AUTO_TOPUP_THRESHOLD_RANGE),
            "amount_range": list(settings.AUTO_TOPUP_AMOUNT_RANGE),
        },
    }
