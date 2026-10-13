"""Balance changes. Each one updates the account and writes a journal entry in
one short transaction of its own, so concurrent requests can never spend the
same rubles twice: a debit is a single `UPDATE ... WHERE balance >= amount`.
"""

from dataclasses import dataclass
import logging
from typing import Optional
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.auth.context import get_current_owner_id, get_current_owner_is_admin
from models.sql.billing import BillingAccount, BillingEntry
from services.billing import settings
from services.database import async_session_maker
from utils.datetime_utils import get_current_utc_datetime

LOGGER = logging.getLogger(__name__)

PRESENTATION = "presentation"


class InsufficientFunds(Exception):
    def __init__(self, needed: int, balance: int):
        super().__init__(f"needed {needed}, balance {balance}")
        self.needed = needed
        self.balance = balance


@dataclass(frozen=True)
class Charge:
    """A debit that can be refunded; amount 0 means nothing was taken."""

    user_id: Optional[uuid.UUID] = None
    amount: int = 0
    entry_id: Optional[uuid.UUID] = None


FREE = Charge()


def payer() -> Optional[uuid.UUID]:
    """The signed-in user if they pay. Administrators, the single-user mode
    (no sign-in) and a disabled billing pay nothing."""
    if not settings.billing_enabled():
        return None
    owner = get_current_owner_id()
    if owner is None or get_current_owner_is_admin():
        return None
    return owner


async def _account(session: AsyncSession, user_id: uuid.UUID) -> BillingAccount:
    """The user's account, opened with the signup bonus on first use."""
    account = await session.get(BillingAccount, user_id)
    if account is not None:
        return account
    bonus = settings.signup_bonus()
    session.add(BillingAccount(user_id=user_id, balance=bonus))
    if bonus:
        session.add(
            BillingEntry(
                user_id=user_id,
                amount=bonus,
                balance_after=bonus,
                kind="bonus",
                reason="signup",
                idempotency_key=f"bonus:{user_id}",
            )
        )
    try:
        await session.commit()
    except IntegrityError:
        # Opened by a concurrent request.
        await session.rollback()
    return await session.get(BillingAccount, user_id, populate_existing=True)


async def _balance(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        await session.scalar(select(BillingAccount.balance).where(BillingAccount.user_id == user_id)) or 0
    )


async def apply_change(
    session: AsyncSession,
    user_id: uuid.UUID,
    delta: int,
    *,
    kind: str,
    reason: str = "",
    reference: Optional[str] = None,
    details: Optional[dict] = None,
    settled: bool = True,
    idempotency_key: Optional[str] = None,
) -> Optional[BillingEntry]:
    """Change the balance and journal it, without committing. Returns None when
    a debit does not fit the balance (nothing changes)."""
    condition = [BillingAccount.user_id == user_id]
    if delta < 0:
        condition.append(BillingAccount.balance >= -delta)
    result = await session.execute(
        update(BillingAccount)
        .where(*condition)
        .values(balance=BillingAccount.balance + delta, updated_at=get_current_utc_datetime())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return None
    entry = BillingEntry(
        user_id=user_id,
        amount=delta,
        balance_after=await _balance(session, user_id),
        kind=kind,
        reason=reason,
        reference=reference,
        details=details,
        settled=settled,
        idempotency_key=idempotency_key,
    )
    session.add(entry)
    return entry


class AlreadyCharged(Exception):
    """The idempotency key was used: this exact charge exists."""


async def balance_of(user_id: uuid.UUID) -> int:
    async with async_session_maker() as session:
        return (await _account(session, user_id)).balance


async def charge(
    user_id: Optional[uuid.UUID],
    amount: int,
    *,
    reason: str,
    reference: Optional[str] = None,
    details: Optional[dict] = None,
    settled: bool = True,
    idempotency_key: Optional[str] = None,
) -> Charge:
    """Take `amount` or raise InsufficientFunds; free for user None / amount 0."""
    if user_id is None or amount <= 0:
        return FREE
    async with async_session_maker() as session:
        await _account(session, user_id)
        entry = await apply_change(
            session,
            user_id,
            -amount,
            kind="charge",
            reason=reason,
            reference=reference,
            details=details,
            settled=settled,
            idempotency_key=idempotency_key,
        )
        if entry is None:
            await session.rollback()
            raise InsufficientFunds(amount, await _balance(session, user_id))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise AlreadyCharged(idempotency_key)
        return Charge(user_id, amount, entry.id)


async def refund(charged: Charge, *, note: str = "") -> None:
    """Give a charge back (once, however many times it is called)."""
    if charged.entry_id is None:
        return
    async with async_session_maker() as session:
        await _refund_entry(session, charged.entry_id, note)
        await session.commit()


async def _refund_entry(session: AsyncSession, entry_id: uuid.UUID, note: str) -> None:
    claimed = await session.execute(
        update(BillingEntry)
        .where(BillingEntry.id == entry_id, BillingEntry.refunded == False, BillingEntry.amount < 0)  # noqa: E712
        .values(refunded=True)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        return
    original = await session.get(BillingEntry, entry_id)
    await apply_change(
        session,
        original.user_id,
        -original.amount,
        kind="refund",
        reason=original.reason,
        reference=str(original.id),
        details={"note": note} if note else None,
        idempotency_key=f"refund:{original.id}",
    )
    LOGGER.info("Refunded %s RUB to %s (%s)", -original.amount, original.user_id, original.reason)


def _pending_presentation(user_id: uuid.UUID, presentation_id: uuid.UUID):
    return (
        BillingEntry.user_id == user_id,
        BillingEntry.kind == "charge",
        BillingEntry.reason == PRESENTATION,
        BillingEntry.reference == str(presentation_id),
        BillingEntry.settled == False,  # noqa: E712
        BillingEntry.refunded == False,  # noqa: E712
    )


async def charge_presentation(
    user_id: Optional[uuid.UUID], presentation_id: uuid.UUID, slides: int, *, top_up: bool = True
) -> Charge:
    """Pay for generating `slides` slides. An unfinished earlier generation of the
    same presentation (an error, a closed tab) is already paid: only extra slides
    cost more, and with top_up=False nothing more. The charge is settled when the
    slides are saved."""
    per_slide = settings.price_per_slide()
    if user_id is None or per_slide <= 0 or slides <= 0:
        return FREE
    reference = str(presentation_id)
    async with async_session_maker() as session:
        pending = (await session.scalars(select(BillingEntry).where(*_pending_presentation(user_id, presentation_id)))).all()
        paid = sum(int((entry.details or {}).get("slides") or 0) for entry in pending)
        attempts = await session.scalar(
            select(func.count())
            .select_from(BillingEntry)
            .where(
                BillingEntry.user_id == user_id,
                BillingEntry.kind == "charge",
                BillingEntry.reason == PRESENTATION,
                BillingEntry.reference == reference,
            )
        )
    extra = slides - paid
    if extra <= 0 or (pending and not top_up):
        return FREE
    try:
        return await charge(
            user_id,
            extra * per_slide,
            reason=PRESENTATION,
            reference=reference,
            details={"slides": extra, "per_slide": per_slide},
            settled=False,
            # Two clicks at once compute the same key: only one of them pays.
            idempotency_key=f"presentation:{reference}:{attempts}",
        )
    except AlreadyCharged:
        return FREE


async def settle_presentation(user_id: Optional[uuid.UUID], presentation_id: uuid.UUID) -> None:
    """The slides are saved: the next generation of this presentation is paid anew."""
    if user_id is None:
        return
    async with async_session_maker() as session:
        await session.execute(
            update(BillingEntry)
            .where(*_pending_presentation(user_id, presentation_id))
            .values(settled=True)
            .execution_options(synchronize_session=False)
        )
        await session.commit()


async def refund_presentation(user_id: Optional[uuid.UUID], presentation_id: uuid.UUID, *, note: str = "") -> None:
    """Generation failed for good (API calls): give back what it took."""
    if user_id is None:
        return
    async with async_session_maker() as session:
        ids = (await session.scalars(select(BillingEntry.id).where(*_pending_presentation(user_id, presentation_id)))).all()
        for entry_id in ids:
            await _refund_entry(session, entry_id, note)
        await session.commit()


async def admin_adjust(user_id: uuid.UUID, amount: int, *, mode: str, admin_id: Optional[uuid.UUID], note: str = "") -> int:
    """Add (may be negative) or set the balance; it never goes below zero."""
    async with async_session_maker() as session:
        current = (await _account(session, user_id)).balance
        target = amount if mode == "set" else current + amount
        delta = max(0, target) - current
        if delta:
            entry = await apply_change(
                session,
                user_id,
                delta,
                kind="admin",
                reason="admin",
                details={"note": note[:200], "by": str(admin_id) if admin_id else None},
            )
            if entry is None:  # spent meanwhile: take what is left
                await session.rollback()
                return await admin_adjust(user_id, amount, mode=mode, admin_id=admin_id, note=note)
            await session.commit()
        return await _balance(session, user_id)


async def history(user_id: uuid.UUID, limit: int = 50) -> list[BillingEntry]:
    async with async_session_maker() as session:
        await _account(session, user_id)
        rows = await session.scalars(
            select(BillingEntry)
            .where(BillingEntry.user_id == user_id)
            .order_by(BillingEntry.created_at.desc())
            .limit(limit)
        )
        return list(rows)


def entry_dict(entry: BillingEntry) -> dict:
    return {
        "id": str(entry.id),
        "amount": entry.amount,
        "balance_after": entry.balance_after,
        "kind": entry.kind,
        "reason": entry.reason,
        "reference": entry.reference,
        "pending": entry.kind == "charge" and not entry.settled and not entry.refunded,
        "refunded": entry.refunded,
        "details": entry.details or {},
        "created_at": entry.created_at,
    }
