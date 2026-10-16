"""add storage objects (copies of app data files in external storage)

Revision ID: c3e5a7b9d1f4
Revises: b2d4f6a8c0e3
Create Date: 2026-10-16 12:00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "c3e5a7b9d1f4"
down_revision: str | None = "b2d4f6a8c0e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "storage_objects" not in tables:
        op.create_table(
            "storage_objects",
            sa.Column("path", sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=False),
            sa.Column("remote_path", sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=False),
            sa.Column("url", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=False),
            sa.Column("fallback_url", sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=True),
            sa.Column("sha256", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
            sa.Column("size", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("path"),
        )


def downgrade() -> None:
    op.drop_table("storage_objects")
