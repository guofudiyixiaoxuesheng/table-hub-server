"""完成知识库资源上传接口。"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.idempotency.service import begin_idempotency, complete_idempotency
from app.modules.knowledge.actions import complete_upload_action
from app.modules.knowledge.schemas import CompleteKnowledgeDocumentUploadRequest

router = APIRouter()


@router.post("/uploads/{upload_id}/complete")
async def complete_knowledge_upload(
    request: Request,
    upload_id: uuid.UUID,
    payload: CompleteKnowledgeDocumentUploadRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    guard = await begin_idempotency(
        request=request,
        db=db,
        access=access,
        scope=f"knowledge.uploads.{upload_id}.complete",
    )
    if guard.is_replay:
        return guard.replay_response
    data = await complete_upload_action(upload_id, payload, access.store_id, db)
    response = success_response(
        message="剧本文件夹上传完成", data=data.model_dump(mode="json", by_alias=True)
    )
    await complete_idempotency(guard=guard, response_body=response, db=db)
    return response
