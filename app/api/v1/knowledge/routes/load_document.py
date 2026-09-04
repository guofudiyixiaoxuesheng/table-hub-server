"""知识库文档加载接口。"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.database import get_database
from app.core.security import StoreManagerAccess
from app.modules.idempotency.service import begin_idempotency, complete_idempotency
from app.modules.knowledge.actions import (
    delete_knowledge_file_action,
    get_asset_preview_url_action,
    get_loaded_markdown_action,
    list_loaded_files_action,
    load_document_action,
    load_single_file_action,
    save_manual_parsed_text_action,
)
from app.modules.knowledge.schemas import ManualParsedTextRequest

router = APIRouter()


@router.post("/{document_id}/versions/{version_id}/load")
async def load_knowledge_document(
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
        scope=f"knowledge.{document_id}.versions.{version_id}.load",
    )
    if guard.is_replay:
        return guard.replay_response
    data = await load_document_action(document_id, version_id, access.store_id, db)
    response = success_response(
        message="文档加载完成", data=data.model_dump(mode="json", by_alias=True)
    )
    await complete_idempotency(guard=guard, response_body=response, db=db)
    return response


@router.get("/{document_id}/versions/{version_id}/loaded-files")
async def list_loaded_files(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await list_loaded_files_action(document_id, version_id, access.store_id, db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.delete("/{document_id}/versions/{version_id}/files/{file_id}")
async def delete_knowledge_file(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    file_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await delete_knowledge_file_action(
        document_id, version_id, file_id, access.store_id, db
    )
    return success_response(
        message="文件已删除",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.post("/{document_id}/versions/{version_id}/files/{file_id}/load")
async def load_knowledge_file(
    request: Request,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    file_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    guard = await begin_idempotency(
        request=request,
        db=db,
        access=access,
        scope=f"knowledge.{document_id}.versions.{version_id}.files.{file_id}.load",
    )
    if guard.is_replay:
        return guard.replay_response
    data = await load_single_file_action(
        document_id, version_id, file_id, access.store_id, db
    )
    response = success_response(
        message="单个文件加载完成", data=data.model_dump(mode="json", by_alias=True)
    )
    await complete_idempotency(guard=guard, response_body=response, db=db)
    return response


@router.post("/{document_id}/versions/{version_id}/files/{file_id}/manual-text")
async def save_manual_parsed_text(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    file_id: uuid.UUID,
    payload: ManualParsedTextRequest,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await save_manual_parsed_text_action(
        document_id, version_id, file_id, access.store_id, payload, db
    )
    return success_response(
        message="补录文本已保存",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.get(
    "/{document_id}/versions/{version_id}/loaded-files/{parsed_file_id}/markdown"
)
async def get_loaded_markdown(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    parsed_file_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await get_loaded_markdown_action(
        document_id, version_id, parsed_file_id, access.store_id, db
    )
    return success_response(data=data.model_dump(mode="json", by_alias=True))


@router.get("/assets/{asset_id}/preview-url")
async def get_asset_preview_url(
    asset_id: uuid.UUID,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await get_asset_preview_url_action(asset_id, access.store_id, db)
    return success_response(data=data.model_dump(mode="json", by_alias=True))
