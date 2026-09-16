"""add reusable script marketing image library

Revision ID: u8b9c0d1e2f3
Revises: t7a8b9c0d1e2
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u8b9c0d1e2f3"
down_revision: str | None = "t7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "script_marketing_images",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("source_asset_id", sa.UUID(), nullable=True),
        sa.Column("generation_id", sa.String(length=64), nullable=True),
        sa.Column("image_kind", sa.String(length=20), nullable=False, server_default="cover"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="generating"),
        sa.Column("object_key", sa.String(length=1024), nullable=True),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("final_prompt", sa.Text(), nullable=True),
        sa.Column("style_profile_id", sa.UUID(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_asset_id"], ["script_marketing_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["style_profile_id"], ["script_art_reference_style_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_script_marketing_images_store_document",
        "script_marketing_images",
        ["store_id", "document_id", "created_at"],
    )
    op.create_index(
        "ix_script_marketing_images_source_asset",
        "script_marketing_images",
        ["source_asset_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_script_marketing_images_source_asset", table_name="script_marketing_images")
    op.drop_index("ix_script_marketing_images_store_document", table_name="script_marketing_images")
    op.drop_table("script_marketing_images")
