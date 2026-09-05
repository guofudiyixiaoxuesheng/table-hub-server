"""add script opening manuals

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a4b5c6d7e8"
down_revision: str | Sequence[str] | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


opening_manual_status = postgresql.ENUM(
    "draft",
    "generating",
    "ready",
    "failed",
    "approved",
    name="opening_manual_status",
    create_type=False,
)


def upgrade() -> None:
    opening_manual_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "script_opening_manuals",
        sa.Column("id", sa.UUID(), nullable=False, comment="主持人手册ID"),
        sa.Column("store_id", sa.UUID(), nullable=False, comment="门店ID，用于区分不同门店的数据归属"),
        sa.Column("document_id", sa.UUID(), nullable=False, comment="知识库文档ID，例如某一个剧本资料"),
        sa.Column("version_id", sa.UUID(), nullable=True, comment="知识库版本ID，表示该主持人手册基于哪一次上传版本生成"),
        sa.Column("manual_version_no", sa.Integer(), server_default="1", nullable=False, comment="主持人手册版本号，同一剧本可多次生成或迭代"),
        sa.Column("title", sa.String(length=220), nullable=False, comment="主持人手册标题"),
        sa.Column("style", sa.String(length=40), server_default="professional", nullable=False, comment="生成风格：professional=专业版，simple=简洁版，training=培训版"),
        sa.Column("target_dm_level", sa.String(length=40), server_default="newbie", nullable=False, comment="目标DM水平：newbie=新手DM，experienced=熟练DM"),
        sa.Column("extra_requirement", sa.Text(), nullable=True, comment="店长补充要求或迭代意见"),
        sa.Column("outline", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="手册大纲结构，便于前端按章节展示"),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="每个章节的生成结果摘要和状态"),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False, comment="生成时引用的知识库来源文件列表"),
        sa.Column("markdown_key", sa.String(length=1024), nullable=True, comment="完整Markdown文件在OSS中的存储路径"),
        sa.Column("markdown_preview", sa.Text(), nullable=True, comment="Markdown内容预览，用于列表页快速展示"),
        sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False, comment="AI或规则校验结果，例如是否缺少流程、话术、风险提示"),
        sa.Column("status", opening_manual_status, server_default="draft", nullable=False, comment="生成状态：draft=草稿，generating=生成中，ready=已完成，failed=失败，approved=已确认正式使用"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="生成失败时的错误信息"),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True, comment="触发生成的用户ID"),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=True, comment="确认正式使用该手册的用户ID"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True, comment="店长确认该手册为正式版本的时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opening_manuals_store_document", "script_opening_manuals", ["store_id", "document_id", "created_at"])
    op.create_index("ix_opening_manuals_status_created", "script_opening_manuals", ["store_id", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_opening_manuals_status_created", table_name="script_opening_manuals")
    op.drop_index("ix_opening_manuals_store_document", table_name="script_opening_manuals")
    op.drop_table("script_opening_manuals")
    opening_manual_status.drop(op.get_bind(), checkfirst=True)
