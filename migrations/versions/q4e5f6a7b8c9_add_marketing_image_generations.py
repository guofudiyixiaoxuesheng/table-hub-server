"""persist script marketing image generation history

Revision ID: q4e5f6a7b8c9
Revises: p3e4f5a6b7c8
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "q4e5f6a7b8c9"
down_revision: str | None = "p3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "image_generations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("script_marketing_assets", "image_generations")
