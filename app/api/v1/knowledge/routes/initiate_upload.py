"""初始化知识库资源上传接口。"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.knowledge.actions import initiate_upload_action
from app.modules.knowledge.schemas import InitiateKnowledgeDocumentUploadRequest

router = APIRouter()


@router.post("/uploads/initiate", status_code=status.HTTP_201_CREATED)
async def initiate_knowledge_upload(
    payload: InitiateKnowledgeDocumentUploadRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await initiate_upload_action(payload, access.store_id, db)
    return success_response(
        message="上传会话创建成功", data=data.model_dump(mode="json", by_alias=True)
    )
