"""剧本 AI 视觉素材生产线 ORM 模型。

这条生产线负责：
1. 从剧本档案/RAG 中提炼视觉档案
2. 选择可复用的视觉风格模板
3. 生成主图、详情图、朋友圈图等候选图
4. 店长确认某张图为正式素材
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScriptVisualProfileStatus(str, enum.Enum):
    """剧本视觉档案状态。"""

    DRAFT = "draft"
    READY = "ready"
    FAILED = "failed"
    APPROVED = "approved"


class ScriptVisualAssetStatus(str, enum.Enum):
    """视觉素材状态。"""

    DRAFT = "draft"
    READY = "ready"
    FAILED = "failed"
    SELECTED = "selected"


class ScriptVisualProfile(Base):
    """单个剧本独有的视觉档案。

    它不是最终图片，而是这个剧本的“视觉 DNA”：
    时代、场景、色彩、符号、氛围、人物视觉、版权/剧透禁忌。
    """

    __tablename__ = "script_visual_profiles"
    __table_args__ = (
        Index("ix_script_visual_profiles_store_document", "store_id", "document_id"),
        Index(
            "ix_script_visual_profiles_store_status", "store_id", "status", "updated_at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, comment="剧本视觉档案ID"
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        comment="门店ID，用于多门店数据隔离",
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的知识库剧本文档ID",
    )
    script_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("script_profiles.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联的结构化剧本档案ID，可为空；有剧本档案时优先使用",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="剧本名称")
    era: Mapped[str | None] = mapped_column(
        String(120), nullable=True, comment="时代背景，例如民国上海、现代校园、古风王朝"
    )
    world_setting: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="世界观/故事空间的视觉描述"
    )
    main_scenes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="核心场景，例如高宅、窗边、旧上海街道、密室、宴会厅",
    )
    visual_symbols: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="核心视觉符号，例如旗袍、西装、窗户、香烟、窃听器、旧报纸",
    )
    color_palette: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="推荐主色调，例如深蓝、暗金、酒红、黑色",
    )
    atmosphere_keywords: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="氛围关键词，例如悬疑、暧昧、压抑、荒诞、欢乐",
    )
    character_visuals: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="人物视觉设定，例如角色公开身份、服装、道具、情绪；避免写剧透身份",
    )
    spoiler_safe_rules: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="生图时的剧透安全规则，例如不要暴露凶手、隐藏身份、最终反转",
    )
    copyright_safe_rules: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="版权安全规则，例如不要复刻发行海报、不要出现原logo、不要照搬人物姿势",
    )
    reference_image_urls: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="参考图URL，可来自知识库解析出的图片或店长上传图片",
    )
    confidence_score: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="AI提炼置信度/完整度，0-100"
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=ScriptVisualProfileStatus.DRAFT.value,
        server_default=ScriptVisualProfileStatus.DRAFT.value,
        comment="视觉档案状态：draft=草稿，ready=可用，failed=失败，approved=已确认",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="生成失败原因"
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="触发生成的用户ID",
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="确认视觉档案的用户ID",
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="确认时间"
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


class VisualStylePreset(Base):
    """可复用的视觉风格模板。

    这不是单个剧本独有的，而是所有剧本都可以选择的风格。
    """

    __tablename__ = "visual_style_presets"
    __table_args__ = (
        Index(
            "ix_visual_style_presets_store_active",
            "store_id",
            "is_active",
            "sort_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, comment="视觉风格模板ID"
    )
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=True,
        comment="门店ID；为空表示系统内置模板",
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="模板名称，例如民国悬疑电影感"
    )
    style_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="风格类型，例如 cinematic, anime, horror, comedy",
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="给店长看的风格说明"
    )
    prompt_template: Mapped[str] = mapped_column(
        Text, nullable=False, comment="用于拼接最终生图 prompt 的风格模板"
    )
    negative_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="负向提示词，例如避免文字变形、避免血腥等"
    )
    recommended_aspect_ratios: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="推荐比例，例如 1:1、3:4、9:16、16:9",
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否系统内置模板",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", comment="是否启用"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
        comment="排序值，越小越靠前",
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


class ScriptVisualAsset(Base):
    """AI 生成的视觉候选图或正式图。"""

    __tablename__ = "script_visual_assets"
    __table_args__ = (
        Index(
            "ix_script_visual_assets_store_document",
            "store_id",
            "document_id",
            "created_at",
        ),
        Index(
            "ix_script_visual_assets_profile_usage",
            "visual_profile_id",
            "usage_type",
            "is_selected",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, comment="视觉素材ID"
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        comment="门店ID",
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联剧本文档ID",
    )
    visual_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("script_visual_profiles.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联视觉档案ID",
    )
    style_preset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("visual_style_presets.id", ondelete="SET NULL"),
        nullable=True,
        comment="生成时使用的视觉风格模板ID",
    )
    usage_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        comment="素材用途：session_cover=拼车主图，session_detail=详情图，moments_poster=朋友圈图，character_portrait=人物图",
    )
    usage_label: Mapped[str] = mapped_column(
        String(80), nullable=False, comment="素材用途中文名"
    )
    prompt: Mapped[str] = mapped_column(
        Text, nullable=False, comment="最终用于生成图片的 prompt"
    )
    negative_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="负向提示词"
    )
    aspect_ratio: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1:1",
        server_default="1:1",
        comment="图片比例，例如 1:1、3:4、9:16",
    )
    object_key: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, comment="图片在 OSS 中的 object key"
    )
    image_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True, comment="图片可访问URL"
    )
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=ScriptVisualAssetStatus.DRAFT.value,
        server_default=ScriptVisualAssetStatus.DRAFT.value,
        comment="素材状态：draft=草稿，ready=已生成，failed=失败，selected=已选为正式",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="生成失败原因"
    )
    is_selected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否被店长选为正式素材",
    )
    selected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="选为正式素材的时间"
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="创建素材的用户ID",
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
