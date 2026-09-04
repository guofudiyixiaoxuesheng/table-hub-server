"""统一知识库文档、版本、文件和上传会话 ORM 模型。"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.core.config import settings
from app.core.database import Base


class PgVector(UserDefinedType[list[float]]):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect):
        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(str(item) for item in value) + "]"

        return process

    def result_processor(self, dialect, coltype):
        def process(value: object) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, list):
                return [float(item) for item in value]
            text = str(value).strip("[]")
            return [float(item) for item in text.split(",") if item]

        return process


class KnowledgeDocumentStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class KnowledgeVersionStatus(str, enum.Enum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class KnowledgeFileStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"


class KnowledgeParsedFileStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    SKIPPED = "skipped"
    FAILED = "failed"


class KnowledgeParsedAssetType(str, enum.Enum):
    IMAGE = "image"
    TABLE = "table"
    FORMULA = "formula"


class KnowledgeChunkStatus(str, enum.Enum):
    READY = "ready"
    FAILED = "failed"


class KnowledgeEmbeddingStatus(str, enum.Enum):
    READY = "ready"
    FAILED = "failed"


class KnowledgeChunkType(str, enum.Enum):
    STORY = "story"
    TASK = "task"
    CHARACTER_IMPRESSION = "character_impression"
    RULE = "rule"
    IMAGE = "image"
    NOTE = "note"


class UploadSessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


class KnowledgeResourceType(str, enum.Enum):
    SCRIPT = "script"
    STORE_RULE = "store_rule"
    FAQ = "faq"
    ACTIVITY = "activity"
    OTHER = "other"


class ScriptGenre(str, enum.Enum):
    MYSTERY_HARDCORE = "mystery_hardcore"
    HONKAKU = "honkaku"
    HENKAKU = "henkaku"
    RESTORATION = "restoration"
    EMOTIONAL = "emotional"
    MECHANISM = "mechanism"
    FACTION = "faction"
    COMEDY = "comedy"
    HORROR = "horror"


class ScriptGenreOption(Base):
    """门店可维护的剧本类型字典。

    这里不再依赖 PostgreSQL enum 扩展剧本类型，避免每新增一个类型都要改 enum。
    knowledge_documents.script_genre 存 value，展示时通过这张表拿中文 label。
    """

    __tablename__ = "script_genre_options"
    __table_args__ = (
        UniqueConstraint("store_id", "value", name="uq_script_genre_options_store_value"),
        Index("ix_script_genre_options_store_active_sort", "store_id", "is_active", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (Index("ix_knowledge_documents_store_status", "store_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    resource_type: Mapped[KnowledgeResourceType] = mapped_column(
        Enum(
            KnowledgeResourceType,
            name="knowledge_resource_type",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeResourceType.OTHER,
        server_default=KnowledgeResourceType.OTHER.value,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    script_genre: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[KnowledgeDocumentStatus] = mapped_column(
        Enum(
            KnowledgeDocumentStatus,
            name="knowledge_document_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeDocumentStatus.ACTIVE,
        server_default=KnowledgeDocumentStatus.ACTIVE.value,
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "knowledge_versions.id",
            name="fk_knowledge_documents_active_version_id_knowledge_versions",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    versions: Mapped[list[KnowledgeVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="KnowledgeVersion.document_id",
    )


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_label",
            name="uq_knowledge_versions_document_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[KnowledgeVersionStatus] = mapped_column(
        Enum(
            KnowledgeVersionStatus,
            name="knowledge_version_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeVersionStatus.UPLOADING,
        server_default=KnowledgeVersionStatus.UPLOADING.value,
    )
    manifest_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_count: Mapped[int] = mapped_column(nullable=False)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    document: Mapped[KnowledgeDocument] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )
    files: Mapped[list[KnowledgeFile]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    parsed_files: Mapped[list[KnowledgeParsedFile]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    parsed_assets: Mapped[list[KnowledgeParsedAsset]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    chunk_embeddings: Mapped[list[KnowledgeChunkEmbedding]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    upload_sessions: Mapped[list[KnowledgeUploadSession]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "client_file_id",
            name="uq_knowledge_files_version_client",
        ),
        UniqueConstraint(
            "version_id", "relative_path", name="uq_knowledge_files_version_path"
        ),
        UniqueConstraint("object_key", name="uq_knowledge_files_object_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_file_id: Mapped[str] = mapped_column(String(120), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_modified: Mapped[int] = mapped_column(BigInteger, nullable=False)
    etag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[KnowledgeFileStatus] = mapped_column(
        Enum(
            KnowledgeFileStatus,
            name="knowledge_file_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeFileStatus.PENDING,
        server_default=KnowledgeFileStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    version: Mapped[KnowledgeVersion] = relationship(back_populates="files")


class KnowledgeParsedFile(Base):
    __tablename__ = "knowledge_parsed_files"
    __table_args__ = (
        UniqueConstraint("file_id", name="uq_knowledge_parsed_files_file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    loader_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[KnowledgeParsedFileStatus] = mapped_column(
        Enum(
            KnowledgeParsedFileStatus,
            name="knowledge_parsed_file_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeParsedFileStatus.PENDING,
        server_default=KnowledgeParsedFileStatus.PENDING.value,
    )
    markdown_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    text_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    char_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    version: Mapped[KnowledgeVersion] = relationship(back_populates="parsed_files")
    file: Mapped[KnowledgeFile] = relationship()
    assets: Mapped[list[KnowledgeParsedAsset]] = relationship(
        back_populates="parsed_file", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="parsed_file", cascade="all, delete-orphan"
    )


class KnowledgeParsedAsset(Base):
    __tablename__ = "knowledge_parsed_assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parsed_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_parsed_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type: Mapped[KnowledgeParsedAssetType] = mapped_column(
        Enum(
            KnowledgeParsedAssetType,
            name="knowledge_parsed_asset_type",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeParsedAssetType.IMAGE,
        server_default=KnowledgeParsedAssetType.IMAGE.value,
    )
    asset_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    vlm_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    version: Mapped[KnowledgeVersion] = relationship(back_populates="parsed_assets")
    parsed_file: Mapped[KnowledgeParsedFile] = relationship(back_populates="assets")
    source_file: Mapped[KnowledgeFile] = relationship()


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "parsed_file_id",
            "chunk_index",
            name="uq_knowledge_chunks_parsed_file_index",
        ),
        Index("ix_knowledge_chunks_version_type", "version_id", "chunk_type"),
        Index("ix_knowledge_chunks_role_act", "role_name", "act"),
        Index(
            "ix_knowledge_chunks_bm25",
            "id",
            "title",
            "content",
            "act",
            "role_name",
            "chunk_type",
            "version_id",
            "file_id",
            postgresql_using="bm25",
            postgresql_with={"key_field": "id"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parsed_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_parsed_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[KnowledgeChunkType] = mapped_column(
        Enum(
            KnowledgeChunkType,
            name="knowledge_chunk_type",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeChunkType.NOTE,
        server_default=KnowledgeChunkType.NOTE.value,
    )
    status: Mapped[KnowledgeChunkStatus] = mapped_column(
        Enum(
            KnowledgeChunkStatus,
            name="knowledge_chunk_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeChunkStatus.READY,
        server_default=KnowledgeChunkStatus.READY.value,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    act: Mapped[str | None] = mapped_column(String(80), nullable=True)
    role_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    extra_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    version: Mapped[KnowledgeVersion] = relationship(back_populates="chunks")
    parsed_file: Mapped[KnowledgeParsedFile] = relationship(back_populates="chunks")
    file: Mapped[KnowledgeFile] = relationship()
    embeddings: Mapped[list[KnowledgeChunkEmbedding]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan"
    )


class KnowledgeChunkEmbedding(Base):
    __tablename__ = "knowledge_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "embedding_model",
            name="uq_knowledge_chunk_embeddings_chunk_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        PgVector(settings.EMBEDDING_DIMENSION), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[KnowledgeEmbeddingStatus] = mapped_column(
        Enum(
            KnowledgeEmbeddingStatus,
            name="knowledge_embedding_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=KnowledgeEmbeddingStatus.READY,
        server_default=KnowledgeEmbeddingStatus.READY.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    chunk: Mapped[KnowledgeChunk] = relationship(back_populates="embeddings")
    version: Mapped[KnowledgeVersion] = relationship(back_populates="chunk_embeddings")
    file: Mapped[KnowledgeFile] = relationship()


class KnowledgeUploadSession(Base):
    __tablename__ = "knowledge_upload_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[UploadSessionStatus] = mapped_column(
        Enum(
            UploadSessionStatus,
            name="knowledge_upload_session_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=UploadSessionStatus.ACTIVE,
        server_default=UploadSessionStatus.ACTIVE.value,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    version: Mapped[KnowledgeVersion] = relationship(
        back_populates="upload_sessions"
    )
