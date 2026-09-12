"""store final image prompts for marketing assets

Revision ID: o2d3e4f5a6b7
Revises: n1c2d3e4f5a6
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "o2d3e4f5a6b7"
down_revision: str | None = "n1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "final_image_prompts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_marketing_assets", "final_image_prompts")
