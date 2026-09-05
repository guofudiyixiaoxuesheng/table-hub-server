"""add script profiles

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g4b5c6d7e8f9"
down_revision: str | Sequence[str] | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


script_profile_review_status = postgresql.ENUM(
    "draft",
    "needs_review",
    "approved",
    "failed",
    name="script_profile_review_status",
    create_type=False,
)


def upgrade() -> None:
    script_profile_review_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "script_profiles",
        sa.Column("id", sa.UUID(), nullable=False, comment="剧本档案ID"),
        sa.Column("store_id", sa.UUID(), nullable=False, comment="门店ID，用于多门店数据隔离"),
        sa.Column("document_id", sa.UUID(), nullable=False, comment="关联的知识库文档ID，一般是一套剧本资料"),
        sa.Column("version_id", sa.UUID(), nullable=True, comment="生成档案时使用的知识库版本ID"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="剧本正式名称"),
        sa.Column("alias_names", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="剧本别名，方便后续 AI 识别用户口语化搜索"),
        sa.Column("genres", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="剧本类型中文标签，例如推理、欢乐、机制、变格"),
        sa.Column("player_count_min", sa.Integer(), nullable=True, comment="建议最少玩家数"),
        sa.Column("player_count_max", sa.Integer(), nullable=True, comment="建议最多玩家数"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True, comment="预估开本时长，单位分钟"),
        sa.Column("difficulty", sa.String(length=80), nullable=True, comment="玩家难度，例如新手友好、进阶、硬核"),
        sa.Column("dm_difficulty", sa.String(length=80), nullable=True, comment="DM主持难度，例如新手可开、中等、较难"),
        sa.Column("summary", sa.Text(), nullable=True, comment="玩家可见简介，默认不剧透"),
        sa.Column("story_background", sa.Text(), nullable=True, comment="故事背景摘要，可用于详情页和客服介绍"),
        sa.Column("truth_summary", sa.Text(), nullable=True, comment="真相摘要，含剧透信息，仅后台/DM可见"),
        sa.Column("selling_points", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="玩家可见卖点列表"),
        sa.Column("suitable_players", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="适合玩家画像"),
        sa.Column("core_mechanics", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="核心机制/玩法摘要"),
        sa.Column("roles", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="角色信息草稿"),
        sa.Column("material_checklist", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="开本物料清单"),
        sa.Column("opening_risks", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="开本风险和控场提醒"),
        sa.Column("spoiler_notes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="剧透注意事项"),
        sa.Column("source_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="生成档案引用的知识库chunk ID列表"),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="生成档案引用的来源文件路径"),
        sa.Column("confidence_score", sa.Integer(), nullable=True, comment="AI抽取置信度/完整度，0-100"),
        sa.Column("review_status", script_profile_review_status, server_default="draft", nullable=False, comment="确认状态：draft=AI草稿，needs_review=需确认，approved=已确认，failed=失败"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="生成失败原因"),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True, comment="触发生成的用户ID"),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True, comment="确认档案正式可用的用户ID"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True, comment="确认时间"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="软删除时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_script_profiles_store_document", "script_profiles", ["store_id", "document_id"])
    op.create_index("ix_script_profiles_store_status", "script_profiles", ["store_id", "review_status", "updated_at"])
    op.create_index(op.f("ix_script_profiles_store_id"), "script_profiles", ["store_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_script_profiles_store_id"), table_name="script_profiles")
    op.drop_index("ix_script_profiles_store_status", table_name="script_profiles")
    op.drop_index("ix_script_profiles_store_document", table_name="script_profiles")
    op.drop_table("script_profiles")
    script_profile_review_status.drop(op.get_bind(), checkfirst=True)
