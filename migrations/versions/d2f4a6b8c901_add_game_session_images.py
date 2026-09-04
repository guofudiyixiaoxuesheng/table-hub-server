"""add game session images

Revision ID: d2f4a6b8c901
Revises: a1b2c3d4e5f6
Create Date: 2026-09-01 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2f4a6b8c901"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("game_sessions", sa.Column("cover_image_source", sa.String(length=32), nullable=True))
    op.add_column("game_sessions", sa.Column("cover_image_url", sa.String(length=2048), nullable=True))
    op.add_column("game_sessions", sa.Column("detail_image_source", sa.String(length=32), nullable=True))
    op.add_column(
        "game_sessions",
        sa.Column(
            "detail_image_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("game_sessions", "detail_image_urls")
    op.drop_column("game_sessions", "detail_image_source")
    op.drop_column("game_sessions", "cover_image_url")
    op.drop_column("game_sessions", "cover_image_source")
