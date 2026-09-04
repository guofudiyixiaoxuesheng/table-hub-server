"""add script marketing assets

Revision ID: c9e8d7f6a5b4
Revises: b8d1f3a5c7e9
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9e8d7f6a5b4"
down_revision: str | Sequence[str] | None = "b8d1f3a5c7e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_enum = postgresql.ENUM("draft", "approved", name="script_marketing_asset_status", create_type=False)
    status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "script_marketing_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=True),
        sa.Column("version_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column("purpose", sa.String(length=40), server_default="script_profile", nullable=False),
        sa.Column("tone", sa.String(length=80), server_default="新手友好、商业宣传", nullable=False),
        sa.Column("manager_feedback", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("selling_points", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("suitable_players", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("cover_prompt", sa.Text(), nullable=False),
        sa.Column("detail_copy", sa.Text(), nullable=False),
        sa.Column("detail_image_prompts", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("risk_notes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("status", status_enum, server_default="draft", nullable=False),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_script_marketing_assets_document_status", "script_marketing_assets", ["document_id", "status", "created_at"])
    op.create_index("ix_script_marketing_assets_store_document", "script_marketing_assets", ["store_id", "document_id"])


def downgrade() -> None:
    op.drop_index("ix_script_marketing_assets_store_document", table_name="script_marketing_assets")
    op.drop_index("ix_script_marketing_assets_document_status", table_name="script_marketing_assets")
    op.drop_table("script_marketing_assets")
    postgresql.ENUM(name="script_marketing_asset_status").drop(op.get_bind(), checkfirst=True)
