"""软删除知识库资源。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.models import UploadSessionStatus
from app.modules.knowledge.repository import get_document_with_versions


async def delete_document_action(
    document_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> None:
    document = await get_document_with_versions(document_id, store_id, db)
    if document is None:
        raise KnowledgeDocumentNotFoundError("知识库资源不存在或已删除")

    now = datetime.now(UTC)
    document.deleted_at = now
    document.active_version_id = None
    for version in document.versions:
        for upload_session in version.upload_sessions:
            if upload_session.status is UploadSessionStatus.ACTIVE:
                upload_session.status = UploadSessionStatus.EXPIRED
    await db.flush()
