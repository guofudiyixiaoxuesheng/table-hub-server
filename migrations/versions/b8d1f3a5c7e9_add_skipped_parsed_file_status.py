"""add skipped parsed file status

Revision ID: b8d1f3a5c7e9
Revises: a7c9d2e4f6b8
Create Date: 2026-09-03 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8d1f3a5c7e9"
down_revision: str | Sequence[str] | None = "a7c9d2e4f6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE knowledge_parsed_file_status ADD VALUE IF NOT EXISTS 'skipped'")


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally not attempted.
    pass
