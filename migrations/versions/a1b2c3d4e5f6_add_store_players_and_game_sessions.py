"""add store players and game sessions

Revision ID: a1b2c3d4e5f6
Revises: 5d1e2f3a4b6c
Create Date: 2026-09-01 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "5d1e2f3a4b6c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    game_session_status = postgresql.ENUM(
        "recruiting",
        "full",
        "cancelled",
        "completed",
        name="game_session_status",
        create_type=False,
    )
    session_join_source = postgresql.ENUM(
        "h5",
        "manual",
        "wechat_chat",
        name="session_join_source",
        create_type=False,
    )
    session_player_status = postgresql.ENUM(
        "pending",
        "confirmed",
        "cancelled",
        name="session_player_status",
        create_type=False,
    )
    postgresql.ENUM(
        "recruiting",
        "full",
        "cancelled",
        "completed",
        name="game_session_status",
    ).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(
        "h5",
        "manual",
        "wechat_chat",
        name="session_join_source",
    ).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(
        "pending",
        "confirmed",
        "cancelled",
        name="session_player_status",
    ).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "store_players",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("preference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "user_id", name="uq_store_players_store_user"),
    )
    op.create_index("ix_store_players_store", "store_players", ["store_id"])
    op.create_index(op.f("ix_store_players_store_id"), "store_players", ["store_id"])
    op.create_index(op.f("ix_store_players_user_id"), "store_players", ["user_id"])

    op.create_table(
        "game_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("script_document_id", sa.UUID(), nullable=True),
        sa.Column("dm_user_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("script_name", sa.String(length=200), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("min_players", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("status", game_session_status, server_default="recruiting", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["dm_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["script_document_id"], ["knowledge_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_game_sessions_store_start_time", "game_sessions", ["store_id", "start_time"])
    op.create_index("ix_game_sessions_store_status", "game_sessions", ["store_id", "status"])
    op.create_index(op.f("ix_game_sessions_dm_user_id"), "game_sessions", ["dm_user_id"])
    op.create_index(op.f("ix_game_sessions_script_document_id"), "game_sessions", ["script_document_id"])
    op.create_index(op.f("ix_game_sessions_store_id"), "game_sessions", ["store_id"])

    op.create_table(
        "session_players",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("player_name", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("seat_count", sa.Integer(), nullable=False),
        sa.Column("reservation_code", sa.String(length=12), nullable=False),
        sa.Column("source", session_join_source, server_default="manual", nullable=False),
        sa.Column("status", session_player_status, server_default="pending", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["game_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_code"),
    )
    op.create_index("ix_session_players_session_status", "session_players", ["session_id", "status"])
    op.create_index("ix_session_players_user", "session_players", ["user_id"])
    op.create_index(op.f("ix_session_players_session_id"), "session_players", ["session_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_session_players_session_id"), table_name="session_players")
    op.drop_index("ix_session_players_user", table_name="session_players")
    op.drop_index("ix_session_players_session_status", table_name="session_players")
    op.drop_table("session_players")
    op.drop_index(op.f("ix_game_sessions_store_id"), table_name="game_sessions")
    op.drop_index(op.f("ix_game_sessions_script_document_id"), table_name="game_sessions")
    op.drop_index(op.f("ix_game_sessions_dm_user_id"), table_name="game_sessions")
    op.drop_index("ix_game_sessions_store_status", table_name="game_sessions")
    op.drop_index("ix_game_sessions_store_start_time", table_name="game_sessions")
    op.drop_table("game_sessions")
    op.drop_index(op.f("ix_store_players_user_id"), table_name="store_players")
    op.drop_index(op.f("ix_store_players_store_id"), table_name="store_players")
    op.drop_index("ix_store_players_store", table_name="store_players")
    op.drop_table("store_players")
    sa.Enum(name="session_player_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="session_join_source").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="game_session_status").drop(op.get_bind(), checkfirst=True)
