"""AI 生成 DM / 主持人开本手册的 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpeningManualStatus(str, enum.Enum):
    """主持人手册生成状态。"""

    DRAFT = "draft"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    APPROVED = "approved"


class ScriptOpeningManual(Base):
    """某个剧本知识库版本生成的一版主持人手册。"""

    __tablename__ = "script_opening_manuals"
    __table_args__ = (
        Index("ix_opening_manuals_store_document", "store_id", "document_id", "created_at"),
        Index("ix_opening_manuals_status_created", "store_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, comment="主持人手册ID")
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        comment="门店ID，用于区分不同门店的数据归属",
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="知识库文档ID，例如某一个剧本资料",
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="知识库版本ID，表示该主持人手册基于哪一次上传版本生成",
    )
    manual_version_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="主持人手册版本号，同一剧本可多次生成或迭代",
    )
    title: Mapped[str] = mapped_column(String(220), nullable=False, comment="主持人手册标题")
    style: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="professional",
        server_default="professional",
        comment="生成风格：professional=专业版，simple=简洁版，training=培训版",
    )
    target_dm_level: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="newbie",
        server_default="newbie",
        comment="目标DM水平：newbie=新手DM，experienced=熟练DM",
    )
    extra_requirement: Mapped[str | None] = mapped_column(Text, nullable=True, comment="店长补充要求或迭代意见")
    outline: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="手册大纲结构，便于前端按章节展示",
    )
    sections: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="每个章节的生成结果摘要和状态",
    )
    sources: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="生成时引用的知识库来源文件列表",
    )
    markdown_key: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="完整Markdown文件在OSS中的存储路径",
    )
    markdown_preview: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Markdown内容预览，用于列表页快速展示")
    validation_result: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="AI或规则校验结果，例如是否缺少流程、话术、风险提示",
    )
    status: Mapped[OpeningManualStatus] = mapped_column(
        Enum(
            OpeningManualStatus,
            name="opening_manual_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=OpeningManualStatus.DRAFT,
        server_default=OpeningManualStatus.DRAFT.value,
        comment="生成状态：draft=草稿，generating=生成中，ready=已完成，failed=失败，approved=已确认正式使用",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="生成失败时的错误信息")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="触发生成的用户ID",
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="确认正式使用该手册的用户ID",
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="店长确认该手册为正式版本的时间",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )
