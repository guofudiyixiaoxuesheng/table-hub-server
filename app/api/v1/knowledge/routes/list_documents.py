"""统一展示当前门店的知识库资源。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.knowledge.models import KnowledgeResourceType
from app.modules.knowledge.repository import list_documents
from app.modules.knowledge.schemas import KnowledgeDocumentListItem

router = APIRouter()


@router.get("/documents")
async def get_knowledge_documents(
    access: StoreManagerAccess,
    resource_type: Annotated[
        KnowledgeResourceType | None, Query(alias="resourceType")
    ] = None,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    rows = await list_documents(
        access.store_id,
        resource_type.value if resource_type else None,
        db,
    )
    data = [
        KnowledgeDocumentListItem(
            id=document.id,
            resourceType=document.resource_type,
            name=document.name,
            description=document.description,
            tags=document.tags,
            status=document.status.value,
            activeVersionId=document.active_version_id,
            activeVersion=version.version_label if version else None,
            fileCount=version.file_count if version else 0,
            totalSize=version.total_size if version else 0,
            updatedAt=document.updated_at,
        ).model_dump(mode="json", by_alias=True)
        for document, version in rows
    ]
    return success_response(data=data)
