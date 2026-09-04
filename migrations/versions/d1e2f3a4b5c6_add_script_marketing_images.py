"""add script marketing generated images

Revision ID: d1e2f3a4b5c6
Revises: c9e8d7f6a5b4
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "c9e8d7f6a5b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    image_status = postgresql.ENUM(
        "not_started",
        "generating",
        "ready",
        "failed",
        name="script_marketing_image_status",
    )
    image_status.create(op.get_bind(), checkfirst=True)
    op.add_column("script_marketing_assets", sa.Column("cover_image_key", sa.String(length=1024), nullable=True))
    op.add_column("script_marketing_assets", sa.Column("cover_image_url", sa.String(length=2048), nullable=True))
    op.add_column(
        "script_marketing_assets",
        sa.Column("detail_image_keys", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.add_column(
        "script_marketing_assets",
        sa.Column("detail_image_urls", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "image_status",
            image_status,
            server_default="not_started",
            nullable=False,
        ),
    )
    op.add_column("script_marketing_assets", sa.Column("image_error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("script_marketing_assets", "image_error_message")
    op.drop_column("script_marketing_assets", "image_status")
    op.drop_column("script_marketing_assets", "detail_image_urls")
    op.drop_column("script_marketing_assets", "detail_image_keys")
    op.drop_column("script_marketing_assets", "cover_image_url")
    op.drop_column("script_marketing_assets", "cover_image_key")
    postgresql.ENUM(name="script_marketing_image_status").drop(op.get_bind(), checkfirst=True)
