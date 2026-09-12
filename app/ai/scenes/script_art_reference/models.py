"""剧本杀美术参考素材包 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ArtReferencePackageStatus(str, enum.Enum):
    DRAFT = "draft"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class ArtReferenceImageStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"


class ScriptArtReferencePackage(Base):
    """一次上传的美术参考素材包。

    它可以暂时不绑定知识库剧本，只承载「剧本标题 + 简介 + 一组图片」。
    当同类素材积累到一定数量后，再统一做 LLM 沉淀分析。
    """

    __tablename__ = "script_art_reference_packages"
    __table_args__ = (
        Index("ix_art_ref_packages_store_status", "store_id", "status", "updated_at"),
        Index("ix_art_ref_packages_store_script", "store_id", "script_name"),
        Index("ix_art_ref_packages_style_era", "dominant_style_type", "era_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False, comment="素材包标题")
    script_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="剧本名称")
    script_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="剧本简介")
    script_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    era_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", server_default="unknown")
    dominant_style_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", server_default="unknown")
    region_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", server_default="unknown")
    mood_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    copyright_scope: Mapped[str] = mapped_column(
        String(60), nullable=False, default="reference_only", server_default="reference_only"
    )
    copyright_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ArtReferencePackageStatus.DRAFT.value, server_default=ArtReferencePackageStatus.DRAFT.value
    )
    analysis_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    prompt_brief_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    uploaded_image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    images: Mapped[list[ScriptArtReferenceImage]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="ScriptArtReferenceImage.sort_order",
    )


class ScriptArtReferenceImage(Base):
    """素材包里的单张图片。"""

    __tablename__ = "script_art_reference_images"
    __table_args__ = (
        Index("ix_art_ref_images_package_usage", "package_id", "usage_type", "sort_order"),
        Index("ix_art_ref_images_style_era", "style_type", "era_type"),
        Index("ix_art_ref_images_status", "status"),
        Index("ix_art_ref_images_package_client", "package_id", "client_file_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("script_art_reference_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_file_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="前端本次上传生成的临时文件ID，用于完成上传时回填状态",
    )
    usage_type: Mapped[str] = mapped_column(String(80), nullable=False, default="other", server_default="other")
    style_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", server_default="unknown")
    era_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", server_default="unknown")
    mood_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    composition_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default=ArtReferenceImageStatus.PENDING.value, server_default=ArtReferenceImageStatus.PENDING.value
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    package: Mapped[ScriptArtReferencePackage] = relationship(back_populates="images")


class ScriptArtReferenceStyleProfile(Base):
    """由一批美术参考素材沉淀出的可复用视觉规律档案。"""

    __tablename__ = "script_art_reference_style_profiles"
    __table_args__ = (
        Index("ix_art_ref_style_profiles_store_updated", "store_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sample_package_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    filter_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    analysis_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="ready", server_default="ready")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
