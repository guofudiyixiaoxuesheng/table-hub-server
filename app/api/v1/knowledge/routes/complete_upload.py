"""完成知识库资源上传接口。"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.knowledge.actions import complete_upload_action
from app.modules.knowledge.schemas import CompleteKnowledgeDocumentUploadRequest

router = APIRouter()


@router.post("/uploads/{upload_id}/complete")
async def complete_knowledge_upload(
    upload_id: uuid.UUID,
    payload: CompleteKnowledgeDocumentUploadRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await complete_upload_action(upload_id, payload, access.store_id, db)
    return success_response(
        message="剧本文件夹上传完成", data=data.model_dump(mode="json", by_alias=True)
    )
