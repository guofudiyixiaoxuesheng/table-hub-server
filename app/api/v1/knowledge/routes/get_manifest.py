"""导出剧本版本清单接口。"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.knowledge.actions import get_manifest_action

router = APIRouter()


@router.get("/{document_id}/versions/{version_id}/manifest")
async def get_knowledge_manifest(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await get_manifest_action(document_id, version_id, access.store_id, db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))
