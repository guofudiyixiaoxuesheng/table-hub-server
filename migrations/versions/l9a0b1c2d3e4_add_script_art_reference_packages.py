"""add script art reference packages

Revision ID: l9a0b1c2d3e4
Revises: 52916a882eab
Create Date: 2026-09-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "l9a0b1c2d3e4"
down_revision: str | None = "52916a882eab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "script_art_reference_packages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False, comment="素材包标题"),
        sa.Column("script_name", sa.String(length=200), nullable=False, comment="剧本名称"),
        sa.Column("script_summary", sa.Text(), nullable=True, comment="剧本简介"),
        sa.Column("script_tags", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("era_type", sa.String(length=80), server_default="unknown", nullable=False),
        sa.Column("dominant_style_type", sa.String(length=80), server_default="unknown", nullable=False),
        sa.Column("mood_types", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("copyright_scope", sa.String(length=60), server_default="reference_only", nullable=False),
        sa.Column("copyright_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column("analysis_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("prompt_brief_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("image_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("uploaded_image_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_art_ref_packages_store_status", "script_art_reference_packages", ["store_id", "status", "updated_at"])
    op.create_index("ix_art_ref_packages_store_script", "script_art_reference_packages", ["store_id", "script_name"])
    op.create_index("ix_art_ref_packages_style_era", "script_art_reference_packages", ["dominant_style_type", "era_type"])
    op.create_index(op.f("ix_script_art_reference_packages_store_id"), "script_art_reference_packages", ["store_id"])
    op.create_index(op.f("ix_script_art_reference_packages_document_id"), "script_art_reference_packages", ["document_id"])

    op.create_table(
        "script_art_reference_images",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("package_id", sa.UUID(), nullable=False),
        sa.Column("client_file_id", sa.String(length=120), nullable=False, comment="前端本次上传生成的临时文件ID，用于完成上传时回填状态"),
        sa.Column("usage_type", sa.String(length=80), server_default="other", nullable=False),
        sa.Column("style_type", sa.String(length=80), server_default="unknown", nullable=False),
        sa.Column("era_type", sa.String(length=80), server_default="unknown", nullable=False),
        sa.Column("mood_types", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("composition_types", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("analysis_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["script_art_reference_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_art_ref_images_package_usage", "script_art_reference_images", ["package_id", "usage_type", "sort_order"])
    op.create_index("ix_art_ref_images_style_era", "script_art_reference_images", ["style_type", "era_type"])
    op.create_index("ix_art_ref_images_status", "script_art_reference_images", ["status"])
    op.create_index("ix_art_ref_images_package_client", "script_art_reference_images", ["package_id", "client_file_id"], unique=True)
    op.create_index(op.f("ix_script_art_reference_images_package_id"), "script_art_reference_images", ["package_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_script_art_reference_images_package_id"), table_name="script_art_reference_images")
    op.drop_index("ix_art_ref_images_package_client", table_name="script_art_reference_images")
    op.drop_index("ix_art_ref_images_status", table_name="script_art_reference_images")
    op.drop_index("ix_art_ref_images_style_era", table_name="script_art_reference_images")
    op.drop_index("ix_art_ref_images_package_usage", table_name="script_art_reference_images")
    op.drop_table("script_art_reference_images")

    op.drop_index(op.f("ix_script_art_reference_packages_document_id"), table_name="script_art_reference_packages")
    op.drop_index(op.f("ix_script_art_reference_packages_store_id"), table_name="script_art_reference_packages")
    op.drop_index("ix_art_ref_packages_style_era", table_name="script_art_reference_packages")
    op.drop_index("ix_art_ref_packages_store_script", table_name="script_art_reference_packages")
    op.drop_index("ix_art_ref_packages_store_status", table_name="script_art_reference_packages")
    op.drop_table("script_art_reference_packages")
