"""Billing: a ruble balance per user, an operations journal and YooKassa payments.

Amounts are whole rubles. Balances change only through services/billing/ledger.py,
which updates the account and writes a journal entry in one transaction.
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlmodel import Field, SQLModel

from utils.datetime_utils import get_current_utc_datetime


class BillingAccount(SQLModel, table=True):
    __tablename__ = "billing_accounts"

    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    )
    balance: int = Field(default=0)
    # Email for 54-FZ receipts (Presenton accounts have usernames only).
    receipt_email: Optional[str] = Field(default=None, max_length=254)
    auto_topup_enabled: bool = Field(default=False)
    auto_topup_threshold: int = Field(default=50)
    auto_topup_amount: int = Field(default=500)
    last_auto_topup_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # YooKassa payment_method_id of a card saved for auto top-up.
    saved_method_id: Optional[str] = Field(default=None, max_length=128)
    card_last4: Optional[str] = Field(default=None, max_length=4)
    card_type: Optional[str] = Field(default=None, max_length=32)
    created_at: datetime = Field(
        default_factory=get_current_utc_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_current_utc_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class BillingEntry(SQLModel, table=True):
    """One balance change. kind: bonus | topup | auto_topup | admin | charge | refund."""

    __tablename__ = "billing_entries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    amount: int
    balance_after: int
    kind: str = Field(max_length=16)
    # What it was for: "studio.generate", "studio.edit", "studio.storyboard", "presentation", ...
    reason: str = Field(default="", max_length=64)
    # A presentation id, payment invoice id, the refunded entry id...
    reference: Optional[str] = Field(default=None, max_length=64, index=True)
    idempotency_key: Optional[str] = Field(
        default=None, sa_column=Column(String(160), unique=True, nullable=True)
    )
    # Presentation charges stay unsettled until the slides are saved: a retry reuses them.
    settled: bool = Field(default=True)
    refunded: bool = Field(default=False)
    details: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=get_current_utc_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )


class BillingPayment(SQLModel, table=True):
    """A YooKassa payment. status: pending | completed | failed. kind: topup | auto_topup."""

    __tablename__ = "billing_payments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    )
    invoice_id: str = Field(sa_column=Column(String(64), unique=True, nullable=False))
    provider_payment_id: Optional[str] = Field(default=None, max_length=64, index=True)
    amount: int
    kind: str = Field(default="topup", max_length=16)
    status: str = Field(default="pending", max_length=16)
    save_card: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=get_current_utc_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_current_utc_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
