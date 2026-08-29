"""add knowledge parsed files

Revision ID: 2f7d9b6c4a10
Revises: 8e5c2a6f9b21
Create Date: 2026-08-29 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2f7d9b6c4a10"
down_revision: str | Sequence[str] | None = "8e5c2a6f9b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

parsed_status = postgresql.ENUM(
    "pending",
    "processing",
    "ready",
    "failed",
    name="knowledge_parsed_file_status",
    create_type=False,
)


def upgrade() -> None:
    postgresql.ENUM(
        "pending",
        "processing",
        "ready",
        "failed",
        name="knowledge_parsed_file_status",
    ).create(op.get_bind(), checkfirst=True)
    op.create_table(
        "knowledge_parsed_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("loader_type", sa.String(length=40), nullable=False),
        sa.Column("status", parsed_status, server_default="pending", nullable=False),
        sa.Column("markdown_key", sa.String(length=1024), nullable=True),
        sa.Column("metadata_key", sa.String(length=1024), nullable=True),
        sa.Column("text_sha256", sa.String(length=64), nullable=True),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["knowledge_files.id"], name=op.f("fk_knowledge_parsed_files_file_id_knowledge_files"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], name=op.f("fk_knowledge_parsed_files_version_id_knowledge_versions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_parsed_files")),
        sa.UniqueConstraint("file_id", name="uq_knowledge_parsed_files_file_id"),
    )
    op.create_index(op.f("ix_knowledge_parsed_files_file_id"), "knowledge_parsed_files", ["file_id"], unique=False)
    op.create_index(op.f("ix_knowledge_parsed_files_version_id"), "knowledge_parsed_files", ["version_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_parsed_files_version_id"), table_name="knowledge_parsed_files")
    op.drop_index(op.f("ix_knowledge_parsed_files_file_id"), table_name="knowledge_parsed_files")
    op.drop_table("knowledge_parsed_files")
    parsed_status.drop(op.get_bind(), checkfirst=True)
