"""persist selected art style profile on marketing assets

Revision ID: p3e4f5a6b7c8
Revises: o2d3e4f5a6b7
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p3e4f5a6b7c8"
down_revision: str | None = "o2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "script_marketing_assets",
        sa.Column("style_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_script_marketing_assets_style_profile_id",
        "script_marketing_assets",
        "script_art_reference_style_profiles",
        ["style_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_script_marketing_assets_style_profile_id",
        "script_marketing_assets",
        type_="foreignkey",
    )
    op.drop_column("script_marketing_assets", "style_profile_id")
