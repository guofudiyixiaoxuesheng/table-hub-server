"""add script genre to knowledge documents

Revision ID: 8e5c2a6f9b21
Revises: 31a48daa44dd
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e5c2a6f9b21"
down_revision: str | Sequence[str] | None = "31a48daa44dd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

script_genre = sa.Enum(
    "mystery_hardcore",
    "restoration",
    "emotional",
    "mechanism",
    "faction",
    "comedy",
    "horror",
    name="script_genre",
)


def upgrade() -> None:
    script_genre.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "knowledge_documents",
        sa.Column("script_genre", script_genre, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "script_genre")
    script_genre.drop(op.get_bind(), checkfirst=True)
