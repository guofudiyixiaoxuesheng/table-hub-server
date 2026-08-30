"""add chat message type

Revision ID: 08c2d4e6f9a1
Revises: f6a7b8c9d012
Create Date: 2026-08-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "08c2d4e6f9a1"
down_revision: str | Sequence[str] | None = "f6a7b8c9d012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    chat_message_type = postgresql.ENUM(
        "text",
        "image",
        "file",
        "action_card",
        "system_event",
        "tool_call",
        "tool_result",
        name="chat_message_type",
        create_type=False,
    )
    chat_message_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "chat_messages",
        sa.Column(
            "message_type",
            chat_message_type,
            server_default="text",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "message_type")
    postgresql.ENUM(name="chat_message_type").drop(op.get_bind(), checkfirst=True)
