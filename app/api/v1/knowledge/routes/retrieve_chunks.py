"""知识库检索接口。"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.knowledge.actions import KnowledgeRetriever
from app.modules.knowledge.schemas import KnowledgeRetrieveRequest

router = APIRouter()


@router.post("/{document_id}/versions/{version_id}/retrieve")
async def retrieve_knowledge_chunks(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: KnowledgeRetrieveRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await KnowledgeRetriever(db).retrieve(
        document_id, version_id, access.store_id, payload
    )
    return success_response(data=data.model_dump(mode="json", by_alias=True))
