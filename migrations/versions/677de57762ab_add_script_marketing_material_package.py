"""add script marketing material package

Revision ID: 677de57762ab
Revises: k8f9a0b1c2d3
Create Date: 2026-09-07 18:28:32.261118
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "677de57762ab"
down_revision: str | Sequence[str] | None = "k8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """新增 AI 运营物料包字段。

    注意：这个 migration 只允许修改 script_marketing_assets。
    之前 autogenerate 曾误判要删除 script_profiles / script_opening_manuals，
    那是因为 migrations/env.py 没有导入对应模型，不能保留那些 drop 语句。
    """

    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "usage_type",
            sa.String(length=60),
            server_default="session_recruiting",
            nullable=False,
            comment="物料用途类型，例如 session_recruiting=拼车招募，moments=朋友圈宣传，newbie=新手友好，holiday=节日活动，custom=自定义",
        ),
    )
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "usage_label",
            sa.String(length=80),
            server_default="拼车招募版",
            nullable=False,
            comment="物料用途中文名称，例如拼车招募版、朋友圈种草版、新手友好版",
        ),
    )
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "player_card",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="玩家端拼车卡片物料，例如标题、副标题、简介、主图Prompt和主图URL",
        ),
    )
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "player_detail",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="玩家端详情页物料，例如详情文案、详情图Prompt和详情图URL列表",
        ),
    )
    op.add_column(
        "script_marketing_assets",
        sa.Column(
            "moments",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="朋友圈传播物料，例如朋友圈文案、海报标题、海报Prompt和海报图片URL",
        ),
    )


def downgrade() -> None:
    op.drop_column("script_marketing_assets", "moments")
    op.drop_column("script_marketing_assets", "player_detail")
    op.drop_column("script_marketing_assets", "player_card")
    op.drop_column("script_marketing_assets", "usage_label")
    op.drop_column("script_marketing_assets", "usage_type")
