"""add art reference region type

Revision ID: m0b1c2d3e4f5
Revises: l9a0b1c2d3e4
Create Date: 2026-09-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m0b1c2d3e4f5"
down_revision: str | None = "l9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_art_reference_packages",
        sa.Column(
            "region_type",
            sa.String(length=80),
            server_default="unknown",
            nullable=False,
            comment="国家/地域粗分类，用于素材分桶和后续聚合分析",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_art_reference_packages", "region_type")
