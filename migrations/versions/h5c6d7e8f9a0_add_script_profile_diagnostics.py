"""add script profile diagnostics

Revision ID: h5c6d7e8f9a0
Revises: g4b5c6d7e8f9
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "g4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_profiles",
        sa.Column(
            "retrieval_diagnostics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
            comment="剧本档案生成时的多路召回诊断结果，用于排查哪些资料没有命中",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_profiles", "retrieval_diagnostics")
