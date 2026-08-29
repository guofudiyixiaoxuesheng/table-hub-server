"""add knowledge parsed assets

Revision ID: 4bb9d7a31c02
Revises: 2f7d9b6c4a10
Create Date: 2026-08-29 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4bb9d7a31c02"
down_revision: str | Sequence[str] | None = "2f7d9b6c4a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

asset_type = postgresql.ENUM(
    "image",
    "table",
    "formula",
    name="knowledge_parsed_asset_type",
    create_type=False,
)


def upgrade() -> None:
    postgresql.ENUM(
        "image",
        "table",
        "formula",
        name="knowledge_parsed_asset_type",
    ).create(op.get_bind(), checkfirst=True)
    op.create_table(
        "knowledge_parsed_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("parsed_file_id", sa.Uuid(), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", asset_type, server_default="image", nullable=False),
        sa.Column("asset_key", sa.String(length=1024), nullable=False),
        sa.Column("original_ref", sa.String(length=1024), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("vlm_description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parsed_file_id"], ["knowledge_parsed_files.id"], name=op.f("fk_knowledge_parsed_assets_parsed_file_id_knowledge_parsed_files"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_file_id"], ["knowledge_files.id"], name=op.f("fk_knowledge_parsed_assets_source_file_id_knowledge_files"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], name=op.f("fk_knowledge_parsed_assets_version_id_knowledge_versions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_parsed_assets")),
    )
    op.create_index(op.f("ix_knowledge_parsed_assets_parsed_file_id"), "knowledge_parsed_assets", ["parsed_file_id"], unique=False)
    op.create_index(op.f("ix_knowledge_parsed_assets_source_file_id"), "knowledge_parsed_assets", ["source_file_id"], unique=False)
    op.create_index(op.f("ix_knowledge_parsed_assets_version_id"), "knowledge_parsed_assets", ["version_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_parsed_assets_version_id"), table_name="knowledge_parsed_assets")
    op.drop_index(op.f("ix_knowledge_parsed_assets_source_file_id"), table_name="knowledge_parsed_assets")
    op.drop_index(op.f("ix_knowledge_parsed_assets_parsed_file_id"), table_name="knowledge_parsed_assets")
    op.drop_table("knowledge_parsed_assets")
    asset_type.drop(op.get_bind(), checkfirst=True)
