"""删除知识库资源接口。"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.knowledge.actions import delete_document_action

router = APIRouter()


@router.delete("/{document_id}")
async def delete_knowledge_document(
    document_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    await delete_document_action(document_id, access.store_id, db)
    return success_response(message="知识库资源已删除")
