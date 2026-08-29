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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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
    FAILED = "failed"


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
    RESTORATION = "restoration"
    EMOTIONAL = "emotional"
    MECHANISM = "mechanism"
    FACTION = "faction"
    COMEDY = "comedy"
    HORROR = "horror"


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
    script_genre: Mapped[ScriptGenre | None] = mapped_column(
        Enum(
            ScriptGenre,
            name="script_genre",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=True,
    )
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
