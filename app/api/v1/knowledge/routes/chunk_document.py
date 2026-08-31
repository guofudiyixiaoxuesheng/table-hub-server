"""知识库文档切片接口。"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.idempotency.service import begin_idempotency, complete_idempotency
from app.modules.knowledge.actions import chunk_document_action, list_chunks_action

router = APIRouter()


@router.post("/{document_id}/versions/{version_id}/chunks")
async def chunk_knowledge_document(
    request: Request,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    guard = await begin_idempotency(
        request=request,
        db=db,
        access=access,
        scope=f"knowledge.{document_id}.versions.{version_id}.chunks",
    )
    if guard.is_replay:
        return guard.replay_response
    data = await chunk_document_action(document_id, version_id, access.store_id, db)
    response = success_response(
        message="文档切片完成", data=data.model_dump(mode="json", by_alias=True)
    )
    await complete_idempotency(guard=guard, response_body=response, db=db)
    return response


@router.get("/{document_id}/versions/{version_id}/chunks")
async def list_knowledge_chunks(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await list_chunks_action(document_id, version_id, access.store_id, db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))
