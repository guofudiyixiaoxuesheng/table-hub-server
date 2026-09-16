"""persist script profile background generation status

Revision ID: s6f7a8b9c0d1
Revises: r5e6f7a8b9c0
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s6f7a8b9c0d1"
down_revision: str | None = "r5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_profiles",
        sa.Column(
            "generation_status",
            sa.String(length=24),
            nullable=False,
            server_default="ready",
            comment="后台生成状态：queued=已排队，generating=生成中，ready=完成，failed=失败",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_profiles", "generation_status")
