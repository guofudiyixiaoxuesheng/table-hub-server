"""persist script profile act structure

Revision ID: t7a8b9c0d1e2
Revises: s6f7a8b9c0d1
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "t7a8b9c0d1e2"
down_revision: str | None = "s6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_profiles",
        sa.Column(
            "act_structure",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="跨角色本归并出的分幕结构、公共任务、转场条件与证据来源",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_profiles", "act_structure")
