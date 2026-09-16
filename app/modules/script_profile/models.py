"""剧本档案 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScriptProfileReviewStatus(str, enum.Enum):
    """剧本档案人工确认状态。"""

    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    FAILED = "failed"


class ScriptProfile(Base):
    """某个知识库剧本资料对应的一份结构化剧本档案。"""

    __tablename__ = "script_profiles"
    __table_args__ = (
        Index("ix_script_profiles_store_document", "store_id", "document_id"),
        Index("ix_script_profiles_store_status", "store_id", "review_status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, comment="剧本档案ID")
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="门店ID，用于多门店数据隔离",
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的知识库文档ID，一般是一套剧本资料",
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="生成档案时使用的知识库版本ID",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="剧本正式名称")
    alias_names: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="剧本别名，方便后续 AI 识别用户口语化搜索",
    )
    genres: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="剧本类型中文标签，例如推理、欢乐、机制、变格",
    )
    player_count_min: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="建议最少玩家数")
    player_count_max: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="建议最多玩家数")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="预估开本时长，单位分钟")
    difficulty: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="玩家难度，例如新手友好、进阶、硬核")
    dm_difficulty: Mapped[str | None] = mapped_column(String(80), nullable=True, comment="DM主持难度，例如新手可开、中等、较难")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="玩家可见简介，默认不剧透")
    story_background: Mapped[str | None] = mapped_column(Text, nullable=True, comment="故事背景摘要，可用于详情页和客服介绍")
    truth_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="真相摘要，含剧透信息，仅后台/DM可见")
    selling_points: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="玩家可见卖点列表",
    )
    suitable_players: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="适合玩家画像，例如新手、熟人局、团建、喜欢机制玩家",
    )
    core_mechanics: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="核心机制/玩法摘要",
    )
    roles: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="角色信息草稿，先用JSON保持灵活，后续稳定后可拆角色表",
    )
    relationships: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="人物关系边，例如 A 与 B 的亲属、恋人、敌对、阵营、秘密等关系",
    )
    act_structure: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="跨角色本归并出的分幕结构、公共任务、转场条件与证据来源",
    )
    material_checklist: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="开本物料清单",
    )
    opening_risks: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="开本风险和控场提醒",
    )
    spoiler_notes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="剧透注意事项，提醒哪些内容不能暴露给玩家",
    )
    source_chunk_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="生成档案引用的知识库chunk ID列表，便于回溯来源",
    )
    sources: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="生成档案引用的来源文件路径",
    )
    retrieval_diagnostics: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="剧本档案生成时的多路召回诊断结果，用于排查哪些资料没有命中",
    )
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="AI抽取置信度/完整度，0-100")
    review_status: Mapped[ScriptProfileReviewStatus] = mapped_column(
        Enum(
            ScriptProfileReviewStatus,
            name="script_profile_review_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=ScriptProfileReviewStatus.DRAFT,
        server_default=ScriptProfileReviewStatus.DRAFT.value,
        comment="确认状态：draft=AI草稿，needs_review=需确认，approved=已确认，failed=失败",
    )
    generation_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="ready",
        server_default="ready",
        comment="后台生成状态：queued=已排队，generating=生成中，ready=完成，failed=失败",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="生成失败原因")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="触发生成的用户ID",
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="确认档案正式可用的用户ID",
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="确认时间")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="软删除时间")
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
