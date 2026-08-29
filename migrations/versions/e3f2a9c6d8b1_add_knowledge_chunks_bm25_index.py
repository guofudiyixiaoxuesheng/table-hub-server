"""add knowledge chunks bm25 index

Revision ID: e3f2a9c6d8b1
Revises: c4a7f1e8b2d9
Create Date: 2026-08-29 16:10:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e3f2a9c6d8b1"
down_revision: str | Sequence[str] | None = "c4a7f1e8b2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_bm25
        ON knowledge_chunks
        USING bm25 (
            id,
            title,
            content,
            act,
            role_name,
            chunk_type,
            version_id,
            file_id
        )
        WITH (key_field='id')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_bm25")
