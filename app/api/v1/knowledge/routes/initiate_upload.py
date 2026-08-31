"""初始化知识库资源上传接口。"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.idempotency.service import begin_idempotency, complete_idempotency
from app.modules.knowledge.actions import initiate_upload_action
from app.modules.knowledge.schemas import InitiateKnowledgeDocumentUploadRequest

router = APIRouter()


@router.post("/uploads/initiate", status_code=status.HTTP_201_CREATED)
async def initiate_knowledge_upload(
    request: Request,
    payload: InitiateKnowledgeDocumentUploadRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    guard = await begin_idempotency(
        request=request,
        db=db,
        access=access,
        scope="knowledge.uploads.initiate",
    )
    if guard.is_replay:
        return guard.replay_response
    data = await initiate_upload_action(payload, access.store_id, db)
    response = success_response(
        message="上传会话创建成功", data=data.model_dump(mode="json", by_alias=True)
    )
    await complete_idempotency(guard=guard, response_body=response, db=db)
    return response
