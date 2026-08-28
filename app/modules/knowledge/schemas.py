"""统一知识库上传和展示 API 数据结构。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings
from app.modules.knowledge.models import KnowledgeResourceType


class KnowledgeFileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    client_file_id: str = Field(alias="clientFileId", min_length=1, max_length=120)
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=1024)
    size: int = Field(ge=0)
    content_type: str = Field(alias="contentType", min_length=1, max_length=255)
    last_modified: int = Field(alias="lastModified", ge=0)


class InitiateKnowledgeDocumentUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resource_type: KnowledgeResourceType = Field(alias="resourceType")
    document_id: uuid.UUID | None = Field(default=None, alias="documentId")
    name: str = Field(alias="name", min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    files: list[KnowledgeFileRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_upload(self):
        self.tags = list(dict.fromkeys(tag.strip() for tag in self.tags if tag.strip()))
        if len(self.files) > settings.OSS_MAX_FILES_PER_PACKAGE:
            raise ValueError(
                f"单次最多上传 {settings.OSS_MAX_FILES_PER_PACKAGE} 个文件"
            )
        if sum(item.size for item in self.files) > settings.OSS_MAX_PACKAGE_SIZE_BYTES:
            raise ValueError("知识库资源总大小超出限制")
        return self


class UploadTargetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    client_file_id: str = Field(alias="clientFileId")
    object_key: str = Field(alias="objectKey")
    upload_url: str = Field(alias="uploadUrl")
    headers: dict[str, str] = Field(default_factory=dict)


class InitiateKnowledgeDocumentUploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    upload_id: uuid.UUID = Field(alias="uploadId")
    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    expires_at: datetime = Field(alias="expiresAt")
    files: list[UploadTargetResponse]


class CompletedFileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    client_file_id: str = Field(alias="clientFileId")
    etag: str = ""


class CompleteKnowledgeDocumentUploadRequest(BaseModel):
    files: list[CompletedFileRequest] = Field(min_length=1)


class CompleteKnowledgeDocumentUploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    status: str


class KnowledgeDocumentManifestResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    manifest_version: str = Field(alias="manifestVersion", default="1.0")
    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    store_id: uuid.UUID = Field(alias="storeId")
    resource_type: KnowledgeResourceType = Field(alias="resourceType")
    name: str = Field(alias="name")
    version: str
    description: str | None
    tags: list[str]
    status: str
    files: list[dict[str, object]]


class KnowledgeDocumentListItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    resource_type: KnowledgeResourceType = Field(alias="resourceType")
    name: str
    description: str | None
    tags: list[str]
    status: str
    active_version_id: uuid.UUID | None = Field(alias="activeVersionId")
    active_version: str | None = Field(alias="activeVersion")
    file_count: int = Field(alias="fileCount")
    total_size: int = Field(alias="totalSize")
    updated_at: datetime = Field(alias="updatedAt")
