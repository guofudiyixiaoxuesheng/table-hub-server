"""add rag evaluation jobs

Revision ID: f1a2b3c4d5e6
Revises: e4f6a8b0c123
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e4f6a8b0c123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_enum = postgresql.ENUM(
        "pending", "running", "completed", "failed", "skipped",
        name="rag_evaluation_status",
        create_type=False,
    )
    status_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "rag_evaluation_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=True),
        sa.Column("chat_session_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("guest_id", sa.String(length=120), nullable=True),
        sa.Column("trace_id", sa.String(length=120), nullable=True),
        sa.Column("thread_id", sa.String(length=120), nullable=True),
        sa.Column("scene", sa.String(length=40), server_default="script_rag", nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("document_name", sa.String(length=180), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("contexts_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("citations_json", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("judge_reason", sa.Text(), nullable=True),
        sa.Column("status", status_enum, server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_eval_store_status_created", "rag_evaluation_jobs", ["store_id", "status", "created_at"])
    op.create_index("ix_rag_eval_session_created", "rag_evaluation_jobs", ["chat_session_id", "created_at"])
    op.create_index("ix_rag_eval_document_created", "rag_evaluation_jobs", ["document_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_eval_document_created", table_name="rag_evaluation_jobs")
    op.drop_index("ix_rag_eval_session_created", table_name="rag_evaluation_jobs")
    op.drop_index("ix_rag_eval_store_status_created", table_name="rag_evaluation_jobs")
    op.drop_table("rag_evaluation_jobs")
    postgresql.ENUM(name="rag_evaluation_status").drop(op.get_bind(), checkfirst=True)
