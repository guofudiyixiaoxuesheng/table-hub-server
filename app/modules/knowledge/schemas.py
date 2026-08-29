"""统一知识库上传和展示 API 数据结构。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import settings
from app.modules.knowledge.models import KnowledgeResourceType, ScriptGenre


class KnowledgeFileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    client_file_id: str = Field(alias="clientFileId", min_length=1, max_length=120)
    relative_path: str = Field(alias="relativePath", min_length=1, max_length=1024)
    size: int = Field(ge=0)
    content_type: str = Field(alias="contentType", min_length=1, max_length=255)
    last_modified: int = Field(alias="lastModified", ge=0)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class InitiateKnowledgeDocumentUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    resource_type: KnowledgeResourceType = Field(alias="resourceType")
    document_id: uuid.UUID | None = Field(default=None, alias="documentId")
    name: str = Field(alias="name", min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    script_genre: ScriptGenre | None = Field(default=None, alias="scriptGenre")
    tags: list[str] = Field(default_factory=list, max_length=30)
    files: list[KnowledgeFileRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_upload(self):
        self.tags = list(dict.fromkeys(tag.strip() for tag in self.tags if tag.strip()))
        if self.resource_type is KnowledgeResourceType.SCRIPT and self.script_genre is None:
            raise ValueError("剧本资源必须选择剧本类型")
        if self.resource_type is not KnowledgeResourceType.SCRIPT:
            self.script_genre = None
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
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


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
    script_genre: ScriptGenre | None = Field(default=None, alias="scriptGenre")
    name: str = Field(alias="name")
    version: str
    description: str | None
    tags: list[str]
    status: str
    files: list[dict[str, object]]


class ParsedKnowledgeFileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    file_id: uuid.UUID = Field(alias="fileId")
    relative_path: str = Field(alias="relativePath")
    loader_type: str = Field(alias="loaderType")
    status: str
    markdown_key: str | None = Field(default=None, alias="markdownKey")
    text_sha256: str | None = Field(default=None, alias="textSha256")
    char_count: int = Field(alias="charCount")
    asset_count: int = Field(alias="assetCount")
    error_message: str | None = Field(default=None, alias="errorMessage")
    completed_at: datetime | None = Field(default=None, alias="completedAt")


class LoadKnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    files: list[ParsedKnowledgeFileResponse]


class ParsedMarkdownResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    parsed_file_id: uuid.UUID = Field(alias="parsedFileId")
    file_id: uuid.UUID = Field(alias="fileId")
    relative_path: str = Field(alias="relativePath")
    markdown: str


class AssetPreviewUrlResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    asset_id: uuid.UUID = Field(alias="assetId")
    preview_url: str = Field(alias="previewUrl")


class KnowledgeChunkResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    parsed_file_id: uuid.UUID = Field(alias="parsedFileId")
    file_id: uuid.UUID = Field(alias="fileId")
    relative_path: str = Field(alias="relativePath")
    chunk_index: int = Field(alias="chunkIndex")
    chunk_type: str = Field(alias="chunkType")
    status: str
    title: str | None
    act: str | None
    role_name: str | None = Field(alias="roleName")
    content: str
    content_sha256: str = Field(alias="contentSha256")
    char_count: int = Field(alias="charCount")
    metadata: dict[str, object]
    created_at: datetime = Field(alias="createdAt")


class KnowledgeChunkFileSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_id: uuid.UUID = Field(alias="fileId")
    parsed_file_id: uuid.UUID = Field(alias="parsedFileId")
    relative_path: str = Field(alias="relativePath")
    role_name: str | None = Field(alias="roleName")
    acts: list[str]
    chunk_count: int = Field(alias="chunkCount")
    type_counts: dict[str, int] = Field(alias="typeCounts")
    status: str
    updated_at: datetime | None = Field(alias="updatedAt")


class KnowledgeChunkListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    total_chunks: int = Field(alias="totalChunks")
    chunked_files: int = Field(alias="chunkedFiles")
    total_files: int = Field(alias="totalFiles")
    type_counts: dict[str, int] = Field(alias="typeCounts")
    files: list[KnowledgeChunkFileSummary]
    chunks: list[KnowledgeChunkResponse]


class KnowledgeEmbeddingSummaryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    model: str
    dimension: int
    total_chunks: int = Field(alias="totalChunks")
    embedded_chunks: int = Field(alias="embeddedChunks")
    failed_chunks: int = Field(alias="failedChunks")
    pending_chunks: int = Field(alias="pendingChunks")
    updated_at: datetime | None = Field(alias="updatedAt")


class KnowledgeRetrieveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=8, alias="topK", ge=1, le=30)
    mode: str = Field(default="hybrid", pattern=r"^(bm25|vector|hybrid)$")
    role_name: str | None = Field(default=None, alias="roleName", max_length=120)
    act: str | None = Field(default=None, max_length=80)
    chunk_type: str | None = Field(default=None, alias="chunkType", max_length=40)


class KnowledgeRetrievedChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    chunk_id: uuid.UUID = Field(alias="chunkId")
    file_id: uuid.UUID = Field(alias="fileId")
    relative_path: str = Field(alias="relativePath")
    title: str | None
    act: str | None
    role_name: str | None = Field(alias="roleName")
    chunk_type: str = Field(alias="chunkType")
    content: str
    score: float
    score_type: str = Field(alias="scoreType")


class KnowledgeRetrieveResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: uuid.UUID = Field(alias="documentId")
    version_id: uuid.UUID = Field(alias="versionId")
    query: str
    mode: str
    results: list[KnowledgeRetrievedChunk]


class KnowledgeDocumentListItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    resource_type: KnowledgeResourceType = Field(alias="resourceType")
    script_genre: ScriptGenre | None = Field(default=None, alias="scriptGenre")
    name: str
    description: str | None
    tags: list[str]
    status: str
    active_version_id: uuid.UUID | None = Field(alias="activeVersionId")
    active_version: str | None = Field(alias="activeVersion")
    file_count: int = Field(alias="fileCount")
    total_size: int = Field(alias="totalSize")
    updated_at: datetime = Field(alias="updatedAt")
