"""add script genre options

Revision ID: a7c9d2e4f6b8
Revises: f1a2b3c4d5e6
Create Date: 2026-09-02 00:00:00.000000
"""

from collections.abc import Sequence
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c9d2e4f6b8"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_GENRES = [
    ("mystery_hardcore", "推理本/硬核本", "核心是找凶手、盘逻辑，适合喜欢推理的玩家。", 10),
    ("honkaku", "本格本", "现实可实现的作案手法和逻辑推理。", 20),
    ("henkaku", "变格本", "含灵异、科幻、超自然等非现实设定。", 30),
    ("restoration", "还原本", "重点还原故事真相，常见失忆、拼线索结构。", 40),
    ("emotional", "情感本", "主打角色代入和情绪体验，适合重故事玩家。", 50),
    ("mechanism", "机制本", "包含小游戏、规则博弈、道具或积分机制。", 60),
    ("faction", "阵营本", "分队竞争，同队合作、不同阵营对抗。", 70),
    ("comedy", "欢乐本", "轻松搞笑，适合团建、破冰和新手。", 80),
    ("horror", "恐怖本", "依靠氛围、NPC、音效营造惊悚体验。", 90),
]


def upgrade() -> None:
    op.create_table(
        "script_genre_options",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "value", name="uq_script_genre_options_store_value"),
    )
    op.create_index("ix_script_genre_options_store_id", "script_genre_options", ["store_id"])
    op.create_index(
        "ix_script_genre_options_store_active_sort",
        "script_genre_options",
        ["store_id", "is_active", "sort_order"],
    )

    op.alter_column(
        "knowledge_documents",
        "script_genre",
        existing_type=postgresql.ENUM(name="script_genre"),
        type_=sa.String(length=80),
        postgresql_using="script_genre::text",
        nullable=True,
    )

    stores = sa.table("stores", sa.column("id", sa.UUID()))
    options = sa.table(
        "script_genre_options",
        sa.column("id", sa.UUID()),
        sa.column("store_id", sa.UUID()),
        sa.column("value", sa.String()),
        sa.column("label", sa.String()),
        sa.column("description", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    connection = op.get_bind()
    store_ids = [row[0] for row in connection.execute(sa.select(stores.c.id)).all()]
    if store_ids:
        rows = [
            {
                "id": uuid.uuid4(),
                "store_id": store_id,
                "value": value,
                "label": label,
                "description": description,
                "sort_order": sort_order,
                "is_active": True,
            }
            for store_id in store_ids
            for value, label, description, sort_order in DEFAULT_GENRES
        ]
        op.bulk_insert(options, rows)


def downgrade() -> None:
    op.drop_index("ix_script_genre_options_store_active_sort", table_name="script_genre_options")
    op.drop_index("ix_script_genre_options_store_id", table_name="script_genre_options")
    op.drop_table("script_genre_options")
    op.alter_column(
        "knowledge_documents",
        "script_genre",
        existing_type=sa.String(length=80),
        type_=postgresql.ENUM(
            "mystery_hardcore",
            "restoration",
            "emotional",
            "mechanism",
            "faction",
            "comedy",
            "horror",
            name="script_genre",
        ),
        postgresql_using=(
            "CASE WHEN script_genre IN "
            "('mystery_hardcore','restoration','emotional','mechanism','faction','comedy','horror') "
            "THEN script_genre::script_genre ELSE NULL END"
        ),
        nullable=True,
    )
