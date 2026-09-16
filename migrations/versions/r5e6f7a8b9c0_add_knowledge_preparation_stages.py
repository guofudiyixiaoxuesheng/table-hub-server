"""persist knowledge preparation stage states

Revision ID: r5e6f7a8b9c0
Revises: q4e5f6a7b8c9
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r5e6f7a8b9c0"
down_revision: str | None = "q4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_versions",
        sa.Column(
            "preparation_stages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="AI 整理各阶段的持久化状态：解析、切块、向量化",
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_versions", "preparation_stages")
