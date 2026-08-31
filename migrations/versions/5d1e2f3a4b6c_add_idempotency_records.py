"""add idempotency records

Revision ID: 5d1e2f3a4b6c
Revises: 08c2d4e6f9a1
Create Date: 2026-08-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5d1e2f3a4b6c"
down_revision: str | Sequence[str] | None = "08c2d4e6f9a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=160), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="processing", nullable=False),
        sa.Column("owner_type", sa.String(length=20), nullable=True),
        sa.Column("owner_id", sa.String(length=120), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_records")),
        sa.UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_records_scope_key"),
    )
    op.create_index("ix_idempotency_records_owner", "idempotency_records", ["owner_type", "owner_id"])
    op.create_index("ix_idempotency_records_created_at", "idempotency_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_created_at", table_name="idempotency_records")
    op.drop_index("ix_idempotency_records_owner", table_name="idempotency_records")
    op.drop_table("idempotency_records")
