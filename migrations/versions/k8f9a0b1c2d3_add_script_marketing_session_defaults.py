"""add script marketing session defaults

Revision ID: k8f9a0b1c2d3
Revises: j7e8f9a0b1c2
Create Date: 2026-09-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "k8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "j7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "session_form_defaults",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
            comment="创建场次时可一键填充的表单默认值，例如标题、简介、人数、时长、价格建议和备注",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_marketing_assets", "session_form_defaults")
