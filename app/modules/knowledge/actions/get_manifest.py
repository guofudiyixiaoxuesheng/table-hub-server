"""读取可导出的知识库版本清单。"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.repository import get_version_for_manifest
from app.modules.knowledge.schemas import KnowledgeDocumentManifestResponse


async def get_manifest_action(
    document_id: uuid.UUID, version_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> KnowledgeDocumentManifestResponse:
    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        raise KnowledgeDocumentNotFoundError("知识库版本不存在")
    document = version.document
    return KnowledgeDocumentManifestResponse(
        documentId=document.id,
        versionId=version.id,
        storeId=document.store_id,
        resourceType=document.resource_type,
        scriptGenre=document.script_genre,
        name=document.name,
        version=version.version_label,
        description=document.description,
        tags=document.tags,
        status=version.status.value,
        files=[
            {
                "clientFileId": file.client_file_id,
                "relativePath": file.relative_path,
                "objectKey": file.object_key,
                "contentType": file.content_type,
                "size": file.size,
                "lastModified": file.last_modified,
                "etag": file.etag,
                "sha256": file.sha256,
            }
            for file in version.files
        ],
    )
