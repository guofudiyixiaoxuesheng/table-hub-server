"""add opening manual timeline

Revision ID: j7e8f9a0b1c2
Revises: i6d7e8f9a0b1
Create Date: 2026-09-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "i6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_opening_manuals",
        sa.Column(
            "timeline",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
            comment="开本时间线，用于记录每个阶段的DM动作、玩家动作、物料发放和风险提醒",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_opening_manuals", "timeline")
