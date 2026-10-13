"""add billing tables (ruble balance, journal, YooKassa payments)

Revision ID: b2d4f6a8c0e3
Revises: 026c0ba8b35c
Create Date: 2026-10-13 18:00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "b2d4f6a8c0e3"
down_revision: str | None = "026c0ba8b35c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "billing_accounts" not in tables:
        op.create_table(
            "billing_accounts",
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("balance", sa.Integer(), nullable=False),
            sa.Column("receipt_email", sqlmodel.sql.sqltypes.AutoString(length=254), nullable=True),
            sa.Column("auto_topup_enabled", sa.Boolean(), nullable=False),
            sa.Column("auto_topup_threshold", sa.Integer(), nullable=False),
            sa.Column("auto_topup_amount", sa.Integer(), nullable=False),
            sa.Column("last_auto_topup_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("saved_method_id", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
            sa.Column("card_last4", sqlmodel.sql.sqltypes.AutoString(length=4), nullable=True),
            sa.Column("card_type", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("user_id"),
        )
    if "billing_entries" not in tables:
        op.create_table(
            "billing_entries",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("balance_after", sa.Integer(), nullable=False),
            sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
            sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
            sa.Column("reference", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
            sa.Column("idempotency_key", sa.String(length=160), nullable=True),
            sa.Column("settled", sa.Boolean(), nullable=False),
            sa.Column("refunded", sa.Boolean(), nullable=False),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key"),
        )
        op.create_index(op.f("ix_billing_entries_user_id"), "billing_entries", ["user_id"], unique=False)
        op.create_index(op.f("ix_billing_entries_reference"), "billing_entries", ["reference"], unique=False)
        op.create_index(op.f("ix_billing_entries_created_at"), "billing_entries", ["created_at"], unique=False)
    if "billing_payments" not in tables:
        op.create_table(
            "billing_payments",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("invoice_id", sa.String(length=64), nullable=False),
            sa.Column("provider_payment_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
            sa.Column("save_card", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("invoice_id"),
        )
        op.create_index(op.f("ix_billing_payments_user_id"), "billing_payments", ["user_id"], unique=False)
        op.create_index(
            op.f("ix_billing_payments_provider_payment_id"), "billing_payments", ["provider_payment_id"], unique=False
        )


def downgrade() -> None:
    op.drop_table("billing_payments")
    op.drop_table("billing_entries")
    op.drop_table("billing_accounts")
