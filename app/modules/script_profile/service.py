"""剧本档案业务服务。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.integrations.llm.client import structured_chat_completion
from app.modules.knowledge.actions.retrieve_chunks import KnowledgeRetriever
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeResourceType
from app.modules.knowledge.schemas import KnowledgeRetrieveRequest
from app.modules.script_profile.models import ScriptProfile, ScriptProfileReviewStatus
from app.modules.script_profile.prompts import SCRIPT_PROFILE_SYSTEM_PROMPT, build_script_profile_prompt
from app.modules.script_profile.schemas import (
    ScriptProfileDraft,
    ScriptProfileGenerateRequest,
    ScriptProfileResult,
    ScriptProfileUpdateRequest,
)


class ScriptProfileError(ApplicationError):
    status_code = 422
    code = "script_profile_error"


def _to_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    return []


def _format_context(chunks: list[object]) -> tuple[str, list[str], list[str]]:
    lines: list[str] = []
    sources: list[str] = []
    chunk_ids: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_id = str(getattr(chunk, "chunk_id", None) or getattr(chunk, "chunkId", ""))
        relative_path = str(getattr(chunk, "relative_path", None) or getattr(chunk, "relativePath", ""))
        title = str(getattr(chunk, "title", None) or "未命名片段")
        content = str(getattr(chunk, "content", ""))
        lines.append(f"[{index}] chunk_id={chunk_id}\n来源：{relative_path} / {title}\n{content}")
        if chunk_id:
            chunk_ids.append(chunk_id)
        if relative_path and relative_path not in sources:
            sources.append(relative_path)
    return "\n\n".join(lines), sources, chunk_ids


def _profile_to_result(profile: ScriptProfile) -> ScriptProfileResult:
    return ScriptProfileResult(
        id=profile.id,
        documentId=profile.document_id,
        versionId=profile.version_id,
        name=profile.name,
        aliasNames=profile.alias_names,
        genres=profile.genres,
        playerCountMin=profile.player_count_min,
        playerCountMax=profile.player_count_max,
        durationMinutes=profile.duration_minutes,
        difficulty=profile.difficulty,
        dmDifficulty=profile.dm_difficulty,
        summary=profile.summary,
        storyBackground=profile.story_background,
        truthSummary=profile.truth_summary,
        sellingPoints=profile.selling_points,
        suitablePlayers=profile.suitable_players,
        coreMechanics=profile.core_mechanics,
        roles=profile.roles,
        materialChecklist=profile.material_checklist,
        openingRisks=profile.opening_risks,
        spoilerNotes=profile.spoiler_notes,
        sourceChunkIds=profile.source_chunk_ids,
        sources=profile.sources,
        confidenceScore=profile.confidence_score,
        reviewStatus=profile.review_status.value if hasattr(profile.review_status, "value") else str(profile.review_status),
        errorMessage=profile.error_message,
        approvedAt=profile.approved_at,
        createdAt=profile.created_at,
        updatedAt=profile.updated_at,
    )


async def _get_script_document(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
) -> KnowledgeDocument:
    document = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocument.resource_type == KnowledgeResourceType.SCRIPT,
        )
    )
    if document is None or document.active_version_id is None:
        raise KnowledgeDocumentNotFoundError("剧本资源不存在或还没有有效版本")
    return document


async def get_script_profile_by_document(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
) -> ScriptProfileResult | None:
    profile = await db.scalar(
        select(ScriptProfile)
        .where(
            ScriptProfile.store_id == store_id,
            ScriptProfile.document_id == document_id,
            ScriptProfile.deleted_at.is_(None),
        )
        .order_by(ScriptProfile.updated_at.desc())
    )
    return _profile_to_result(profile) if profile else None


async def generate_script_profile(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: ScriptProfileGenerateRequest,
) -> ScriptProfileResult:
    document = await _get_script_document(db, store_id=store_id, document_id=document_id)

    query = (
        f"为剧本《{document.name}》整理剧本档案。"
        "重点查找：剧本名称 别名 类型 人数 时长 难度 DM难度 故事背景 角色 机制 物料 真相 结局 开本风险 玩家卖点 适合人群。"
    )
    retrieved = await KnowledgeRetriever(db).retrieve(
        document_id=document.id,
        version_id=document.active_version_id,
        store_id=store_id,
        payload=KnowledgeRetrieveRequest(query=query, top_k=18, mode="hybrid"),
    )
    context, sources, chunk_ids = _format_context(retrieved.results)
    if not context:
        raise ScriptProfileError("当前剧本还没有可用于生成档案的内容，请先完成一键整理给 AI 使用")

    draft = await structured_chat_completion(
        ScriptProfileDraft,
        [
            {"role": "system", "content": SCRIPT_PROFILE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_script_profile_prompt(
                    document_name=document.name,
                    document_description=document.description,
                    document_tags=list(document.tags or []),
                    document_genre=document.script_genre,
                    extra_requirement=payload.extra_requirement,
                    context=context,
                ),
            },
        ],
        temperature=0.2,
        max_tokens=2200,
    )

    existing = await db.scalar(
        select(ScriptProfile).where(
            ScriptProfile.store_id == store_id,
            ScriptProfile.document_id == document.id,
            ScriptProfile.deleted_at.is_(None),
        )
    )
    profile = existing or ScriptProfile(
        id=uuid.uuid4(),
        store_id=store_id,
        document_id=document.id,
        created_by_user_id=user_id,
    )
    if existing is None:
        db.add(profile)

    profile.version_id = document.active_version_id
    profile.name = draft.name or document.name
    profile.alias_names = _to_text_list(draft.alias_names)
    profile.genres = _to_text_list(draft.genres)
    profile.player_count_min = draft.player_count_min
    profile.player_count_max = draft.player_count_max
    profile.duration_minutes = draft.duration_minutes
    profile.difficulty = draft.difficulty
    profile.dm_difficulty = draft.dm_difficulty
    profile.summary = draft.summary
    profile.story_background = draft.story_background
    profile.truth_summary = draft.truth_summary
    profile.selling_points = _to_text_list(draft.selling_points)
    profile.suitable_players = _to_text_list(draft.suitable_players)
    profile.core_mechanics = _to_text_list(draft.core_mechanics)
    profile.roles = list(draft.roles or [])
    profile.material_checklist = _to_text_list(draft.material_checklist)
    profile.opening_risks = _to_text_list(draft.opening_risks)
    profile.spoiler_notes = _to_text_list(draft.spoiler_notes)
    profile.source_chunk_ids = chunk_ids
    profile.sources = sources
    profile.confidence_score = draft.confidence_score
    profile.review_status = (
        ScriptProfileReviewStatus.NEEDS_REVIEW
        if draft.confidence_score < 75 or draft.needs_review_reasons
        else ScriptProfileReviewStatus.DRAFT
    )
    profile.error_message = "；".join(draft.needs_review_reasons) if draft.needs_review_reasons else None

    await db.flush()
    return _profile_to_result(profile)


async def update_script_profile(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    profile_id: uuid.UUID,
    payload: ScriptProfileUpdateRequest,
) -> ScriptProfileResult:
    profile = await db.scalar(
        select(ScriptProfile).where(
            ScriptProfile.id == profile_id,
            ScriptProfile.store_id == store_id,
            ScriptProfile.deleted_at.is_(None),
        )
    )
    if profile is None:
        raise KnowledgeDocumentNotFoundError("剧本档案不存在")

    values = payload.model_dump(exclude_unset=True, by_alias=False)
    for key, value in values.items():
        setattr(profile, key, value)
    if profile.review_status == ScriptProfileReviewStatus.APPROVED:
        profile.review_status = ScriptProfileReviewStatus.DRAFT
        profile.approved_by_user_id = None
        profile.approved_at = None
    await db.flush()
    return _profile_to_result(profile)


async def approve_script_profile(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    profile_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ScriptProfileResult:
    profile = await db.scalar(
        select(ScriptProfile).where(
            ScriptProfile.id == profile_id,
            ScriptProfile.store_id == store_id,
            ScriptProfile.deleted_at.is_(None),
        )
    )
    if profile is None:
        raise KnowledgeDocumentNotFoundError("剧本档案不存在")
    profile.review_status = ScriptProfileReviewStatus.APPROVED
    profile.approved_by_user_id = user_id
    profile.approved_at = datetime.now(UTC)
    await db.flush()
    return _profile_to_result(profile)


async def delete_script_profile(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    profile_id: uuid.UUID,
) -> None:
    profile = await db.scalar(
        select(ScriptProfile).where(
            ScriptProfile.id == profile_id,
            ScriptProfile.store_id == store_id,
            ScriptProfile.deleted_at.is_(None),
        )
    )
    if profile is None:
        raise KnowledgeDocumentNotFoundError("剧本档案不存在")
    profile.deleted_at = datetime.now(UTC)
    await db.flush()
