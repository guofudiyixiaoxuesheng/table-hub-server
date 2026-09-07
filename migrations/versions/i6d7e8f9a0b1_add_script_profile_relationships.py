"""add script profile relationships

Revision ID: i6d7e8f9a0b1
Revises: h5c6d7e8f9a0
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "i6d7e8f9a0b1"
down_revision: str | Sequence[str] | None = "h5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_profiles",
        sa.Column(
            "relationships",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
            comment="人物关系边，例如 A 与 B 的亲属、恋人、敌对、阵营、秘密等关系",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_profiles", "relationships")
