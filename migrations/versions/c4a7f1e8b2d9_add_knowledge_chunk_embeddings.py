"""add knowledge chunk embeddings

Revision ID: c4a7f1e8b2d9
Revises: 9a7c2e1d5b44
Create Date: 2026-08-29 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4a7f1e8b2d9"
down_revision: str | Sequence[str] | None = "9a7c2e1d5b44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

embedding_status = postgresql.ENUM(
    "ready",
    "failed",
    name="knowledge_embedding_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    postgresql.ENUM(
        "ready",
        "failed",
        name="knowledge_embedding_status",
    ).create(op.get_bind(), checkfirst=True)
    op.create_table(
        "knowledge_chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", embedding_status, server_default="ready", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"], name=op.f("fk_knowledge_chunk_embeddings_chunk_id_knowledge_chunks"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], name=op.f("fk_knowledge_chunk_embeddings_document_id_knowledge_documents"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["knowledge_files.id"], name=op.f("fk_knowledge_chunk_embeddings_file_id_knowledge_files"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], name=op.f("fk_knowledge_chunk_embeddings_version_id_knowledge_versions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunk_embeddings")),
        sa.UniqueConstraint("chunk_id", "embedding_model", name="uq_knowledge_chunk_embeddings_chunk_model"),
    )
    op.alter_column("knowledge_chunk_embeddings", "embedding", type_=sa.Text)
    op.execute("ALTER TABLE knowledge_chunk_embeddings ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector")
    op.create_index(op.f("ix_knowledge_chunk_embeddings_chunk_id"), "knowledge_chunk_embeddings", ["chunk_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunk_embeddings_document_id"), "knowledge_chunk_embeddings", ["document_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunk_embeddings_file_id"), "knowledge_chunk_embeddings", ["file_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunk_embeddings_version_id"), "knowledge_chunk_embeddings", ["version_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_chunk_embeddings_version_id"), table_name="knowledge_chunk_embeddings")
    op.drop_index(op.f("ix_knowledge_chunk_embeddings_file_id"), table_name="knowledge_chunk_embeddings")
    op.drop_index(op.f("ix_knowledge_chunk_embeddings_document_id"), table_name="knowledge_chunk_embeddings")
    op.drop_index(op.f("ix_knowledge_chunk_embeddings_chunk_id"), table_name="knowledge_chunk_embeddings")
    op.drop_table("knowledge_chunk_embeddings")
    embedding_status.drop(op.get_bind(), checkfirst=True)
