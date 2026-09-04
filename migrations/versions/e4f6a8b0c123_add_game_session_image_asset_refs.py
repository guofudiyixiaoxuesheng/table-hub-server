"""add game session image asset refs

Revision ID: e4f6a8b0c123
Revises: d2f4a6b8c901
Create Date: 2026-09-01 23:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4f6a8b0c123"
down_revision: str | None = "d2f4a6b8c901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("game_sessions", sa.Column("cover_image_asset_id", sa.UUID(), nullable=True))
    op.add_column(
        "game_sessions",
        sa.Column(
            "detail_image_asset_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_game_sessions_cover_image_asset_id"), "game_sessions", ["cover_image_asset_id"])
    op.create_foreign_key(
        "fk_game_sessions_cover_image_asset_id_knowledge_parsed_assets",
        "game_sessions",
        "knowledge_parsed_assets",
        ["cover_image_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_game_sessions_cover_image_asset_id_knowledge_parsed_assets",
        "game_sessions",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_game_sessions_cover_image_asset_id"), table_name="game_sessions")
    op.drop_column("game_sessions", "detail_image_asset_ids")
    op.drop_column("game_sessions", "cover_image_asset_id")
