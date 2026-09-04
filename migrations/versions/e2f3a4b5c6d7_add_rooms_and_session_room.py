"""add rooms and session room relation

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("capacity", sa.Integer(), server_default="6", nullable=False),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rooms_store_id", "rooms", ["store_id"])
    op.create_index("ix_rooms_store_name", "rooms", ["store_id", "name"], unique=True)
    op.create_index("ix_rooms_store_status", "rooms", ["store_id", "status"])
    op.add_column("game_sessions", sa.Column("room_id", sa.UUID(), nullable=True))
    op.create_index("ix_game_sessions_room_id", "game_sessions", ["room_id"])
    op.create_foreign_key(
        "fk_game_sessions_room_id_rooms",
        "game_sessions",
        "rooms",
        ["room_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_game_sessions_room_id_rooms", "game_sessions", type_="foreignkey")
    op.drop_index("ix_game_sessions_room_id", table_name="game_sessions")
    op.drop_column("game_sessions", "room_id")
    op.drop_index("ix_rooms_store_status", table_name="rooms")
    op.drop_index("ix_rooms_store_name", table_name="rooms")
    op.drop_index("ix_rooms_store_id", table_name="rooms")
    op.drop_table("rooms")
