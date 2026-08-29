"""初始化知识库资源上传。"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.storage.oss import OssStorage
from app.modules.knowledge.exceptions import (
    KnowledgeDocumentConflictError,
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentUploadError,
)
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeFile,
    KnowledgeUploadSession,
    KnowledgeVersion,
)
from app.modules.knowledge.pathing import (
    build_version_prefix,
    normalize_relative_path,
)
from app.modules.knowledge.repository import (
    add_upload_graph,
    get_document,
    version_exists,
)
from app.modules.knowledge.schemas import (
    InitiateKnowledgeDocumentUploadRequest,
    InitiateKnowledgeDocumentUploadResponse,
    UploadTargetResponse,
)


async def initiate_upload_action(
    payload: InitiateKnowledgeDocumentUploadRequest,
    store_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> InitiateKnowledgeDocumentUploadResponse:
    document = None
    if payload.document_id:
        document = await get_document(payload.document_id, store_id, db)
        if document is None:
            raise KnowledgeDocumentNotFoundError("知识库资源不存在或不属于当前门店")
        if document.resource_type is not payload.resource_type:
            raise KnowledgeDocumentConflictError("已有资源的类型不可通过新版本修改")
        if await version_exists(document.id, payload.version, db):
            raise KnowledgeDocumentConflictError("该资源版本已存在")

    document = document or KnowledgeDocument(
        id=uuid.uuid4(),
        store_id=store_id,
        resource_type=payload.resource_type,
        name=payload.name,
        description=payload.description,
        script_genre=payload.script_genre,
        tags=payload.tags,
    )
    version_id = uuid.uuid4()
    upload_id = uuid.uuid4()
    prefix = build_version_prefix(store_id, document.id, version_id)
    expires_at = datetime.now(UTC) + timedelta(
        seconds=settings.OSS_PRESIGN_EXPIRES_SECONDS
    )

    normalized_paths = [
        normalize_relative_path(item.relative_path) for item in payload.files
    ]
    if len(set(normalized_paths)) != len(normalized_paths):
        raise KnowledgeDocumentUploadError("文件夹中存在重复相对路径")
    client_ids = [item.client_file_id for item in payload.files]
    if len(set(client_ids)) != len(client_ids):
        raise KnowledgeDocumentUploadError("文件清单中存在重复 clientFileId")

    version = KnowledgeVersion(
        id=version_id,
        document_id=document.id,
        version_label=payload.version,
        manifest_key=f"{prefix}/manifest/manifest.json",
        file_count=len(payload.files),
        total_size=sum(item.size for item in payload.files),
    )
    files = [
        KnowledgeFile(
            id=uuid.uuid4(),
            version_id=version_id,
            client_file_id=item.client_file_id,
            relative_path=relative_path,
            object_key=f"{prefix}/source/{relative_path}",
            content_type=item.content_type,
            size=item.size,
            last_modified=item.last_modified,
            sha256=item.sha256,
        )
        for item, relative_path in zip(payload.files, normalized_paths, strict=True)
    ]
    upload_session = KnowledgeUploadSession(
        id=upload_id, version_id=version_id, expires_at=expires_at
    )

    oss_storage = storage or OssStorage()
    targets = []
    for file in files:
        signed = oss_storage.presign_put(file.object_key, file.content_type)
        targets.append(
            UploadTargetResponse(
                clientFileId=file.client_file_id,
                objectKey=file.object_key,
                uploadUrl=signed.url,
                headers=signed.headers,
            )
        )

    await add_upload_graph(document, version, files, upload_session, db)
    return InitiateKnowledgeDocumentUploadResponse(
        uploadId=upload_id,
        documentId=document.id,
        versionId=version_id,
        expiresAt=expires_at,
        files=targets,
    )
