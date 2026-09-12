"""add art reference style profiles

Revision ID: n1c2d3e4f5a6
Revises: m0b1c2d3e4f5
Create Date: 2026-09-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "n1c2d3e4f5a6"
down_revision: str | None = "m0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "script_art_reference_style_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sample_package_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("filter_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("analysis_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="ready", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_art_ref_style_profiles_store_updated", "script_art_reference_style_profiles", ["store_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_art_ref_style_profiles_store_updated", table_name="script_art_reference_style_profiles")
    op.drop_table("script_art_reference_style_profiles")
