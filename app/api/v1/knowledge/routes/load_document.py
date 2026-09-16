"""知识库文档加载接口。"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_database
from app.core.security import StoreManagerAccess
from app.modules.idempotency.service import begin_idempotency, complete_idempotency
from app.modules.knowledge.actions import (
    chunk_document_action,
    delete_knowledge_file_action,
    embed_chunks_action,
    get_asset_preview_url_action,
    get_loaded_markdown_action,
    list_loaded_files_action,
    load_document_action,
    load_single_file_action,
    save_manual_parsed_text_action,
)
from app.modules.knowledge.models import (
    KnowledgeEmbeddingStatus,
    KnowledgeParsedFileStatus,
    KnowledgeVersion,
    KnowledgeVersionStatus,
)
from app.modules.knowledge.repository import get_version_for_manifest
from app.modules.knowledge.schemas import ManualParsedTextRequest

router = APIRouter()
logger = logging.getLogger(__name__)

_PREPARATION_STAGE_NAMES = ("load", "chunk", "embed")
_PREPARATION_STALE_AFTER = timedelta(minutes=10)


def _stage_is_completed(version: KnowledgeVersion, stage: str) -> bool:
    stage_data = (version.preparation_stages or {}).get(stage, {})
    return isinstance(stage_data, dict) and stage_data.get("status") == "completed"


def _all_preparation_stages_completed(version: KnowledgeVersion) -> bool:
    return all(
        _stage_is_completed(version, stage) for stage in _PREPARATION_STAGE_NAMES
    )


def _has_current_embeddings(version: KnowledgeVersion) -> bool:
    """阶段标记不能替代真实索引校验：确保每个 chunk 都有当前模型和当前内容的向量。"""

    return bool(version.chunks) and all(
        any(
            embedding.embedding_model == settings.EMBEDDING_MODEL
            and embedding.content_sha256 == chunk.content_sha256
            and embedding.status is KnowledgeEmbeddingStatus.READY
            for embedding in chunk.embeddings
        )
        for chunk in version.chunks
    )


def _clear_preparation_stage(version: KnowledgeVersion, stage: str) -> None:
    stages = dict(version.preparation_stages or {})
    stages.pop(stage, None)
    version.preparation_stages = stages


def _next_uncompleted_stage(version: KnowledgeVersion) -> str:
    return next(
        stage
        for stage in _PREPARATION_STAGE_NAMES
        if not _stage_is_completed(version, stage)
    )


def _has_active_preparation(version: KnowledgeVersion) -> bool:
    """仅阻止仍在时限内的任务；进程重启留下的旧 processing 可以重新入队。"""

    now = datetime.now(UTC)
    for stage_data in (version.preparation_stages or {}).values():
        if not isinstance(stage_data, dict) or stage_data.get("status") not in {
            "queued",
            "processing",
        }:
            continue
        updated_at = stage_data.get("updatedAt")
        if not isinstance(updated_at, str):
            continue
        try:
            started_at = datetime.fromisoformat(updated_at)
        except ValueError:
            continue
        if (
            started_at.tzinfo is not None
            and now - started_at < _PREPARATION_STALE_AFTER
        ):
            return True
    return False


def _set_preparation_stage(
    version: KnowledgeVersion,
    stage: str,
    status: str,
    *,
    error_message: str | None = None,
) -> None:
    """以重新赋值方式更新 JSONB，确保 SQLAlchemy 追踪到变更。"""

    stages = dict(version.preparation_stages or {})
    stage_data: dict[str, str] = {
        "status": status,
        "updatedAt": datetime.now(UTC).isoformat(),
    }
    if error_message:
        stage_data["errorMessage"] = error_message[:2000]
    stages[stage] = stage_data
    version.preparation_stages = stages


async def _invalidate_preparation_stages(
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """源文件或解析文本变化后，令派生的切块和向量结果重新进入待处理状态。"""

    version = await get_version_for_manifest(document_id, version_id, store_id, db)
    if version is None:
        return
    version.preparation_stages = {}
    version.status = KnowledgeVersionStatus.UPLOADED
    version.error_message = None
    version.completed_at = None
    await db.flush()


async def _mark_preparation_failed(
    *,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    store_id: uuid.UUID,
    stage: str,
    error: Exception,
) -> None:
    """后台任务异常后，用独立事务留下可供手动刷新查看的失败状态。"""

    async with AsyncSessionLocal() as db:
        version = await get_version_for_manifest(document_id, version_id, store_id, db)
        if version is not None:
            _set_preparation_stage(version, stage, "failed", error_message=str(error))
            version.status = KnowledgeVersionStatus.FAILED
            version.error_message = str(error)[:2000]
            version.completed_at = datetime.now(UTC)
            await db.commit()


async def run_knowledge_preparation_background(
    *, document_id: uuid.UUID, version_id: uuid.UUID, store_id: uuid.UUID
) -> None:
    """独立执行加载、切片和向量化，避免长任务占用浏览器代理连接。"""

    for stage in _PREPARATION_STAGE_NAMES:
        try:
            async with AsyncSessionLocal() as db:
                version = await get_version_for_manifest(
                    document_id, version_id, store_id, db
                )
                if version is None:
                    return
                if _stage_is_completed(version, stage):
                    logger.info(
                        "knowledge preparation stage skipped",
                        extra={
                            "document_id": str(document_id),
                            "version_id": str(version_id),
                            "stage": stage,
                        },
                    )
                    continue

                # 阶段动作与 completed 标记放在同一事务：崩溃后不会出现
                # “数据已经写入，但阶段状态仍显示完成前”的不一致状态。
                _set_preparation_stage(version, stage, "processing")
                logger.info(
                    "knowledge preparation stage started",
                    extra={
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                        "stage": stage,
                    },
                )
                if stage == "load":
                    await load_document_action(document_id, version_id, store_id, db)
                    if any(
                        parsed.status is KnowledgeParsedFileStatus.FAILED
                        for parsed in version.parsed_files
                    ):
                        # 解析器会将单文件错误记录为 FAILED 而不是抛异常；
                        # 此处必须提交这些可诊断的文件状态，不能随事务一起回滚。
                        error_message = "存在文件解析失败，请在文件识别中处理后重试"
                        _set_preparation_stage(
                            version,
                            stage,
                            "failed",
                            error_message=error_message,
                        )
                        version.status = KnowledgeVersionStatus.FAILED
                        version.error_message = error_message
                        version.completed_at = datetime.now(UTC)
                        await db.commit()
                        return
                elif stage == "chunk":
                    await chunk_document_action(document_id, version_id, store_id, db)
                else:
                    summary = await embed_chunks_action(
                        document_id, version_id, store_id, db
                    )
                    if not summary.total_chunks:
                        raise RuntimeError(
                            "没有可向量化的文本切片，请先检查文档识别结果"
                        )
                    if summary.embedded_chunks != summary.total_chunks:
                        raise RuntimeError("部分文本切片未完成向量化，请稍后重试")
                _set_preparation_stage(version, stage, "completed")
                await db.commit()
                logger.info(
                    "knowledge preparation stage completed",
                    extra={
                        "document_id": str(document_id),
                        "version_id": str(version_id),
                        "stage": stage,
                    },
                )
        except Exception as error:  # noqa: BLE001 - 必须写回状态，不能让任务静默失败。
            logger.exception(
                "knowledge preparation stage failed in background",
                extra={
                    "document_id": str(document_id),
                    "version_id": str(version_id),
                    "stage": stage,
                },
            )
            await _mark_preparation_failed(
                document_id=document_id,
                version_id=version_id,
                store_id=store_id,
                stage=stage,
                error=error,
            )
            return

    async with AsyncSessionLocal() as db:
        version = await get_version_for_manifest(document_id, version_id, store_id, db)
        if version is not None:
            version.status = KnowledgeVersionStatus.READY
            version.error_message = None
            version.completed_at = datetime.now(UTC)
            await db.commit()


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


@router.post("/{document_id}/versions/{version_id}/prepare")
async def prepare_knowledge_for_ai(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    """后台整理当前版本，完成后由页面手动刷新读取阶段状态。"""

    version = await get_version_for_manifest(
        document_id, version_id, access.store_id, db
    )
    if version is None:
        from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError

        raise KnowledgeDocumentNotFoundError("知识库版本不存在")
    if _all_preparation_stages_completed(version):
        if _has_current_embeddings(version):
            return success_response(
                message="资料已整理完成，可直接给 AI 使用",
                data={
                    "documentId": str(document_id),
                    "versionId": str(version_id),
                    "status": "ready",
                },
            )
        # 旧任务记录或异常中断可能留下 completed 标记，但没有真实向量；
        # 仅清除 embed，保留已完成的解析与切块，重试时不会重复前两阶段。
        _clear_preparation_stage(version, "embed")
    if version.status is KnowledgeVersionStatus.PROCESSING and _has_active_preparation(
        version
    ):
        return success_response(
            message="资料正在后台整理，请稍后手动刷新查看进度",
            data={
                "documentId": str(document_id),
                "versionId": str(version_id),
                "status": "processing",
            },
        )

    version.status = KnowledgeVersionStatus.PROCESSING
    version.error_message = None
    version.completed_at = None
    _set_preparation_stage(version, _next_uncompleted_stage(version), "queued")
    # 后台任务使用独立 Session，必须先提交，避免它先启动却读到旧版本状态。
    await db.commit()
    background_tasks.add_task(
        run_knowledge_preparation_background,
        document_id=document_id,
        version_id=version_id,
        store_id=access.store_id,
    )
    return success_response(
        message="资料已在后台开始整理，请稍后手动刷新查看进度",
        data={
            "documentId": str(document_id),
            "versionId": str(version_id),
            "status": "processing",
        },
    )


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
    await _invalidate_preparation_stages(
        document_id=document_id,
        version_id=version_id,
        store_id=access.store_id,
        db=db,
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
    await _invalidate_preparation_stages(
        document_id=document_id,
        version_id=version_id,
        store_id=access.store_id,
        db=db,
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
    await _invalidate_preparation_stages(
        document_id=document_id,
        version_id=version_id,
        store_id=access.store_id,
        db=db,
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
