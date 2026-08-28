"""校验 OSS 对象并完成知识库资源上传。"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.storage.oss import ObjectMetadata, OssStorage
from app.modules.knowledge.exceptions import (
    KnowledgeDocumentConflictError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentUploadError,
)
from app.modules.knowledge.models import (
    KnowledgeFileStatus,
    KnowledgeVersionStatus,
    UploadSessionStatus,
)
from app.modules.knowledge.repository import get_upload_session
from app.modules.knowledge.schemas import (
    CompleteKnowledgeDocumentUploadRequest,
    CompleteKnowledgeDocumentUploadResponse,
)


async def _read_metadata(
    storage: OssStorage, object_keys: list[str]
) -> list[ObjectMetadata]:
    semaphore = asyncio.Semaphore(10)

    async def read(key: str) -> ObjectMetadata:
        async with semaphore:
            return await storage.head_object(key)

    return await asyncio.gather(*(read(key) for key in object_keys))


async def complete_upload_action(
    upload_id: uuid.UUID,
    payload: CompleteKnowledgeDocumentUploadRequest,
    store_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> CompleteKnowledgeDocumentUploadResponse:
    upload = await get_upload_session(upload_id, db)
    if upload is None or upload.version.document.store_id != store_id:
        raise KnowledgeDocumentNotFoundError()

    version = upload.version
    document = version.document
    if upload.status is UploadSessionStatus.COMPLETED:
        return CompleteKnowledgeDocumentUploadResponse(
            documentId=document.id, versionId=version.id, status=version.status.value
        )
    if upload.expires_at < datetime.now(UTC):
        upload.status = UploadSessionStatus.EXPIRED
        raise KnowledgeDocumentConflictError("上传会话已过期，请重新初始化")

    reported = {item.client_file_id: item for item in payload.files}
    expected_ids = {item.client_file_id for item in version.files}
    if len(reported) != len(payload.files) or set(reported) != expected_ids:
        raise KnowledgeDocumentUploadError("完成清单与初始化文件集合不一致")

    oss_storage = storage or OssStorage()
    metadata_list = await _read_metadata(
        oss_storage, [file.object_key for file in version.files]
    )
    for file, metadata in zip(version.files, metadata_list, strict=True):
        client_etag = reported[file.client_file_id].etag.strip('"')
        if metadata.size != file.size:
            raise KnowledgeDocumentUploadError(f"OSS 文件大小不一致：{file.relative_path}")
        if client_etag and metadata.etag and client_etag != metadata.etag:
            raise KnowledgeDocumentUploadError(
                f"OSS 文件 ETag 不一致：{file.relative_path}"
            )
        file.etag = metadata.etag
        file.status = KnowledgeFileStatus.VERIFIED

    manifest = {
        "manifestVersion": "1.0",
        "documentId": str(document.id),
        "versionId": str(version.id),
        "storeId": str(document.store_id),
        "resourceType": document.resource_type,
        "name": document.name,
        "version": version.version_label,
        "description": document.description,
        "tags": document.tags,
        "createdAt": version.created_at.isoformat(),
        "files": [
            {
                "clientFileId": file.client_file_id,
                "relativePath": file.relative_path,
                "objectKey": file.object_key,
                "contentType": file.content_type,
                "size": file.size,
                "lastModified": file.last_modified,
                "etag": file.etag,
            }
            for file in version.files
        ],
    }
    await oss_storage.put_json(version.manifest_key, manifest)

    now = datetime.now(UTC)
    upload.status = UploadSessionStatus.COMPLETED
    upload.completed_at = now
    version.status = KnowledgeVersionStatus.UPLOADED
    version.completed_at = now
    document.active_version_id = version.id
    await db.flush()
    return CompleteKnowledgeDocumentUploadResponse(
        documentId=document.id, versionId=version.id, status=version.status.value
    )
