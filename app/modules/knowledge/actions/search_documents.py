"""知识库文档分页搜索。

这个 action 用来统一知识库文档查询能力：

- 后台知识库列表页：分页、模糊搜索、按类型过滤；
- AI/RAG 子图：根据用户提到的剧本名找到 active version；
- 后续弹窗选择剧本、批量处理、导出时也可以复用。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeChunk,
    KnowledgeChunkEmbedding,
    KnowledgeEmbeddingStatus,
    KnowledgeParsedFile,
    KnowledgeParsedFileStatus,
    KnowledgeResourceType,
    KnowledgeVersion,
)
from app.modules.knowledge.schemas import (
    KnowledgeDocumentListItem,
    KnowledgeDocumentSearchResult,
)


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentSearchFilters:
    """知识库文档搜索条件。

    keyword：模糊匹配名称/描述/标签；
    resource_type：按资源类型过滤，如 script/faq/store_rule；
    status：文档状态过滤；
    has_active_version：只看已有 active_version 的文档。
    """

    store_id: uuid.UUID
    keyword: str | None = None
    resource_type: KnowledgeResourceType | None = None
    status: KnowledgeDocumentStatus | None = None
    has_active_version: bool | None = None
    include_deleted: bool = False
    page: int = 1
    page_size: int = 20


def _apply_filters(statement, filters: KnowledgeDocumentSearchFilters):
    statement = statement.where(KnowledgeDocument.store_id == filters.store_id)
    if not filters.include_deleted:
        statement = statement.where(KnowledgeDocument.deleted_at.is_(None))
    if filters.resource_type:
        statement = statement.where(KnowledgeDocument.resource_type == filters.resource_type)
    if filters.status:
        statement = statement.where(KnowledgeDocument.status == filters.status)
    if filters.has_active_version is True:
        statement = statement.where(KnowledgeDocument.active_version_id.is_not(None))
    if filters.has_active_version is False:
        statement = statement.where(KnowledgeDocument.active_version_id.is_(None))
    if filters.keyword:
        keyword = f"%{filters.keyword.strip()}%"
        statement = statement.where(
            or_(
                KnowledgeDocument.name.ilike(keyword),
                KnowledgeDocument.description.ilike(keyword),
                cast(KnowledgeDocument.tags, Text).ilike(keyword),
            )
        )
    return statement


def _to_list_item(
    document: KnowledgeDocument,
    version: KnowledgeVersion | None,
    ai_status: tuple[str, str, int] | None = None,
) -> KnowledgeDocumentListItem:
    status, status_text, pipeline_percent = ai_status or ("not_ready", "未准备", 0)
    return KnowledgeDocumentListItem(
        id=document.id,
        resourceType=document.resource_type,
        scriptGenre=document.script_genre,
        name=document.name,
        description=document.description,
        tags=document.tags,
        status=document.status.value,
        activeVersionId=document.active_version_id,
        activeVersion=version.version_label if version else None,
        fileCount=version.file_count if version else 0,
        totalSize=version.total_size if version else 0,
        updatedAt=document.updated_at,
        aiStatus=status,
        aiStatusText=status_text,
        pipelinePercent=pipeline_percent,
    )


async def _build_ai_status_map(
    version_ids: list[uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, tuple[str, str, int]]:
    if not version_ids:
        return {}

    parsed_rows = (
        await db.execute(
            select(
                KnowledgeParsedFile.version_id,
                func.count().label("total"),
                func.count().filter(KnowledgeParsedFile.status == KnowledgeParsedFileStatus.READY).label("ready"),
                func.count().filter(KnowledgeParsedFile.status == KnowledgeParsedFileStatus.FAILED).label("failed"),
            )
            .where(KnowledgeParsedFile.version_id.in_(version_ids))
            .group_by(KnowledgeParsedFile.version_id)
        )
    ).all()
    chunk_rows = (
        await db.execute(
            select(KnowledgeChunk.version_id, func.count().label("total"))
            .where(KnowledgeChunk.version_id.in_(version_ids))
            .group_by(KnowledgeChunk.version_id)
        )
    ).all()
    embedding_rows = (
        await db.execute(
            select(
                KnowledgeChunkEmbedding.version_id,
                func.count().label("total"),
                func.count().filter(KnowledgeChunkEmbedding.status == KnowledgeEmbeddingStatus.READY).label("ready"),
                func.count().filter(KnowledgeChunkEmbedding.status == KnowledgeEmbeddingStatus.FAILED).label("failed"),
            )
            .where(KnowledgeChunkEmbedding.version_id.in_(version_ids))
            .group_by(KnowledgeChunkEmbedding.version_id)
        )
    ).all()

    parsed = {row.version_id: row for row in parsed_rows}
    chunks = {row.version_id: row for row in chunk_rows}
    embeddings = {row.version_id: row for row in embedding_rows}
    result: dict[uuid.UUID, tuple[str, str, int]] = {}
    for version_id in version_ids:
        parsed_row = parsed.get(version_id)
        chunk_row = chunks.get(version_id)
        embedding_row = embeddings.get(version_id)
        loaded_done = bool(parsed_row and parsed_row.total and parsed_row.ready == parsed_row.total)
        chunk_done = bool(chunk_row and chunk_row.total)
        embedding_done = bool(embedding_row and embedding_row.total and embedding_row.ready == embedding_row.total)
        failed = bool((parsed_row and parsed_row.failed) or (embedding_row and embedding_row.failed))
        completed = len([done for done in [loaded_done, chunk_done, embedding_done] if done])
        percent = round(completed / 3 * 100)
        if loaded_done and chunk_done and embedding_done:
            result[version_id] = ("ready", "可使用", percent)
        elif failed:
            result[version_id] = ("partial_error", "部分异常", percent)
        elif completed:
            result[version_id] = ("processing", "整理中", percent)
        else:
            result[version_id] = ("not_ready", "未准备", percent)
    return result


async def search_knowledge_documents(
    filters: KnowledgeDocumentSearchFilters,
    db: AsyncSession,
) -> KnowledgeDocumentSearchResult:
    """分页搜索知识库文档。"""

    page = max(filters.page, 1)
    page_size = min(max(filters.page_size, 1), 100)
    normalized_filters = replace(filters, page=page, page_size=page_size)

    base_statement = select(KnowledgeDocument.id)
    base_statement = _apply_filters(base_statement, normalized_filters)
    total = await db.scalar(select(func.count()).select_from(base_statement.subquery()))

    statement = (
        select(KnowledgeDocument, KnowledgeVersion)
        .outerjoin(KnowledgeVersion, KnowledgeDocument.active_version_id == KnowledgeVersion.id)
        .order_by(KnowledgeDocument.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    statement = _apply_filters(statement, normalized_filters)
    rows = (await db.execute(statement)).tuples().all()
    version_ids = [version.id for _, version in rows if version]
    ai_status_map = await _build_ai_status_map(version_ids, db)

    return KnowledgeDocumentSearchResult(
        items=[_to_list_item(document, version, ai_status_map.get(version.id) if version else None) for document, version in rows],
        total=total or 0,
        page=page,
        pageSize=page_size,
    )


async def find_active_script_document(
    *,
    store_id: uuid.UUID,
    script_name: str | None,
    db: AsyncSession,
) -> tuple[KnowledgeDocument, KnowledgeVersion] | None:
    """查找一个可用于剧本 RAG 的 active script 文档。"""

    statement = (
        select(KnowledgeDocument, KnowledgeVersion)
        .join(KnowledgeVersion, KnowledgeDocument.active_version_id == KnowledgeVersion.id)
        .where(
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.resource_type == KnowledgeResourceType.SCRIPT,
            KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocument.active_version_id.is_not(None),
        )
        .order_by(KnowledgeDocument.updated_at.desc())
        .limit(1)
    )
    if script_name:
        statement = statement.where(KnowledgeDocument.name.ilike(f"%{script_name.strip()}%"))

    row = (await db.execute(statement)).first()
    if row is None:
        return None
    return row.tuple()
