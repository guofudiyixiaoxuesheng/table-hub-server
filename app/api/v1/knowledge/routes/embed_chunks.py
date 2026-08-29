"""知识库 chunk 向量化接口。"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.knowledge.actions import embed_chunks_action, list_embeddings_action

router = APIRouter()


@router.post("/{document_id}/versions/{version_id}/embeddings")
async def embed_knowledge_chunks(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await embed_chunks_action(document_id, version_id, access.store_id, db)
    return success_response(
        message="向量化完成", data=data.model_dump(mode="json", by_alias=True)
    )


@router.get("/{document_id}/versions/{version_id}/embeddings")
async def list_knowledge_embeddings(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await list_embeddings_action(document_id, version_id, access.store_id, db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))
