"""add chat sessions

Revision ID: f6a7b8c9d012
Revises: e3f2a9c6d8b1
Create Date: 2026-08-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d012"
down_revision: str | Sequence[str] | None = "e3f2a9c6d8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    chat_session_status = postgresql.ENUM(
        "active", "deleted", name="chat_session_status", create_type=False
    )
    chat_message_role = postgresql.ENUM(
        "user", "assistant", "system", name="chat_message_role", create_type=False
    )
    chat_session_status.create(op.get_bind(), checkfirst=True)
    chat_message_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("store_id", sa.UUID(), nullable=True),
        sa.Column("guest_id", sa.String(length=120), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("scene", sa.String(length=40), nullable=True),
        sa.Column(
            "status",
            chat_session_status,
            server_default="active",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_chat_sessions_thread_id", "chat_sessions", ["thread_id"], unique=True)
    op.create_index("ix_chat_sessions_user_updated", "chat_sessions", ["user_id", "updated_at"])
    op.create_index("ix_chat_sessions_guest_updated", "chat_sessions", ["guest_id", "updated_at"])
    op.create_index("ix_chat_sessions_store_updated", "chat_sessions", ["store_id", "updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", chat_message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_session_created", "chat_messages", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_created", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_store_updated", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_guest_updated", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_updated", table_name="chat_sessions")
    op.drop_index("uq_chat_sessions_thread_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    postgresql.ENUM(name="chat_message_role").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="chat_session_status").drop(op.get_bind(), checkfirst=True)
