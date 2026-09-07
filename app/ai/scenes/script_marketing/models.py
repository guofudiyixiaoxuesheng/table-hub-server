"""剧本 AI 运营物料 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScriptMarketingAssetStatus(str, enum.Enum):
    """运营物料版本状态。"""

    DRAFT = "draft"
    APPROVED = "approved"


class ScriptMarketingImageStatus(str, enum.Enum):
    """AI 图片生成状态。"""

    NOT_STARTED = "not_started"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class ScriptMarketingAsset(Base):
    """基于剧本 RAG 生成并由店长确认的运营物料版本。"""

    __tablename__ = "script_marketing_assets"
    __table_args__ = (
        Index(
            "ix_script_marketing_assets_document_status",
            "document_id",
            "status",
            "created_at",
        ),
        Index("ix_script_marketing_assets_store_document", "store_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="SET NULL"), nullable=True
    )
    version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    purpose: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="script_profile"
    )
    tone: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="新手友好、商业宣传"
    )
    manager_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    selling_points: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    suitable_players: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    cover_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    detail_copy: Mapped[str] = mapped_column(Text, nullable=False)
    detail_image_prompts: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    detail_image_keys: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    detail_image_urls: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    session_form_defaults: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="创建场次时可一键填充的表单默认值，例如标题、简介、人数、时长、价格建议和备注",
    )
    image_status: Mapped[ScriptMarketingImageStatus] = mapped_column(
        Enum(
            ScriptMarketingImageStatus,
            name="script_marketing_image_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=ScriptMarketingImageStatus.NOT_STARTED,
        server_default=ScriptMarketingImageStatus.NOT_STARTED.value,
    )
    image_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_notes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    sources: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[ScriptMarketingAssetStatus] = mapped_column(
        Enum(
            ScriptMarketingAssetStatus,
            name="script_marketing_asset_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=ScriptMarketingAssetStatus.DRAFT,
        server_default=ScriptMarketingAssetStatus.DRAFT.value,
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
