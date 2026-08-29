"""add knowledge chunks

Revision ID: 9a7c2e1d5b44
Revises: 4bb9d7a31c02
Create Date: 2026-08-29 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9a7c2e1d5b44"
down_revision: str | Sequence[str] | None = "4bb9d7a31c02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

chunk_type = postgresql.ENUM(
    "story",
    "task",
    "character_impression",
    "rule",
    "image",
    "note",
    name="knowledge_chunk_type",
    create_type=False,
)
chunk_status = postgresql.ENUM(
    "ready",
    "failed",
    name="knowledge_chunk_status",
    create_type=False,
)


def upgrade() -> None:
    postgresql.ENUM(
        "story",
        "task",
        "character_impression",
        "rule",
        "image",
        "note",
        name="knowledge_chunk_type",
    ).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(
        "ready",
        "failed",
        name="knowledge_chunk_status",
    ).create(op.get_bind(), checkfirst=True)
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("parsed_file_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_type", chunk_type, server_default="note", nullable=False),
        sa.Column("status", chunk_status, server_default="ready", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("act", sa.String(length=80), nullable=True),
        sa.Column("role_name", sa.String(length=120), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["knowledge_files.id"], name=op.f("fk_knowledge_chunks_file_id_knowledge_files"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parsed_file_id"], ["knowledge_parsed_files.id"], name=op.f("fk_knowledge_chunks_parsed_file_id_knowledge_parsed_files"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], name=op.f("fk_knowledge_chunks_version_id_knowledge_versions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint("parsed_file_id", "chunk_index", name="uq_knowledge_chunks_parsed_file_index"),
    )
    op.create_index(op.f("ix_knowledge_chunks_document_id"), "knowledge_chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_file_id"), "knowledge_chunks", ["file_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_parsed_file_id"), "knowledge_chunks", ["parsed_file_id"], unique=False)
    op.create_index("ix_knowledge_chunks_role_act", "knowledge_chunks", ["role_name", "act"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_version_id"), "knowledge_chunks", ["version_id"], unique=False)
    op.create_index("ix_knowledge_chunks_version_type", "knowledge_chunks", ["version_id", "chunk_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_version_type", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_version_id"), table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_role_act", table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_parsed_file_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_file_id"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    chunk_status.drop(op.get_bind(), checkfirst=True)
    chunk_type.drop(op.get_bind(), checkfirst=True)
