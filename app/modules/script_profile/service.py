"""剧本档案业务服务。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.integrations.llm.client import structured_chat_completion
from app.modules.knowledge.actions.retrieve_chunks import KnowledgeRetriever
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeResourceType
from app.modules.knowledge.schemas import KnowledgeRetrieveRequest
from app.modules.script_profile.models import ScriptProfile, ScriptProfileReviewStatus
from app.modules.script_profile.prompts import (
    SCRIPT_PROFILE_SYSTEM_PROMPT,
    SCRIPT_RELATIONSHIPS_SYSTEM_PROMPT,
    build_relationships_prompt,
    build_script_profile_prompt,
)
from app.modules.script_profile.schemas import (
    ScriptProfileDraft,
    ScriptProfileGenerateRequest,
    ScriptProfileResult,
    ScriptProfileUpdateRequest,
    ScriptRelationshipsResult,
)


class ProfileRetrievalScene(TypedDict):
    """剧本档案的一路定向召回配置。"""

    key: str
    title: str
    query: str
    top_k: int


PROFILE_RETRIEVAL_SCENES: list[ProfileRetrievalScene] = [
    {
        "key": "basic",
        "title": "基础信息",
        "query": "剧本名称 别名 人数 时长 类型 难度 发行信息 简介 背景",
        "top_k": 8,
    },
    {
        "key": "roles",
        "title": "角色信息",
        "query": "角色列表 人物介绍 玩家角色 性别 身份 职业 阵营 人设 角色小传 人物背景",
        "top_k": 12,
    },
    {
        "key": "relationships",
        "title": "人物关系",
        "query": "你对其他人的印象 认识的人 与某人的关系 过往 秘密 情感关系 亲属关系 阵营关系 敌对关系 恩情 仇恨 误会 角色关系图",
        "top_k": 16,
    },
    {
        "key": "dm_flow",
        "title": "DM流程",
        "query": "DM手册 组织者手册 主持流程 开场话术 分幕流程 控场 节奏",
        "top_k": 10,
    },
    {
        "key": "mechanics",
        "title": "机制规则",
        "query": "游戏规则 机制 计分 任务 道具 线索卡 投票 结算",
        "top_k": 10,
    },
    {
        "key": "truth",
        "title": "真相结局",
        "query": "真相 凶手 复盘 答案 结局 时间线 反转 核心诡计",
        "top_k": 10,
    },
    {
        "key": "materials",
        "title": "物料线索",
        "query": "物料清单 地图 线索 道具 BGM 表格 打印 准备",
        "top_k": 8,
    },
]

MAX_CONTEXT_CHARS_PER_CHUNK = 900
MAX_CONTEXT_CHARS_PER_SCENE = 6500


class ScriptProfileError(ApplicationError):
    status_code = 422
    code = "script_profile_error"


def _to_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [
            item.strip() for item in value.replace("，", ",").split(",") if item.strip()
        ]
    return []


def _format_context(chunks: list[object]) -> tuple[str, list[str], list[str]]:
    lines: list[str] = []
    sources: list[str] = []
    chunk_ids: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_id = str(
            getattr(chunk, "chunk_id", None) or getattr(chunk, "chunkId", "")
        )
        relative_path = str(
            getattr(chunk, "relative_path", None) or getattr(chunk, "relativePath", "")
        )
        title = str(getattr(chunk, "title", None) or "未命名片段")
        content = str(getattr(chunk, "content", ""))
        if len(content) > MAX_CONTEXT_CHARS_PER_CHUNK:
            content = f"{content[:MAX_CONTEXT_CHARS_PER_CHUNK]}...\n[内容过长，已截断]"
        lines.append(
            f"[{index}] chunk_id={chunk_id}\n来源：{relative_path} / {title}\n{content}"
        )
        if chunk_id:
            chunk_ids.append(chunk_id)
        if relative_path and relative_path not in sources:
            sources.append(relative_path)
    return "\n\n".join(lines), sources, chunk_ids


async def retrieve_profile_contexts(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document: KnowledgeDocument,
) -> tuple[dict[str, str], list[str], list[str], list[dict[str, object]]]:
    """按剧本档案字段分多路召回，避免一次大 query 漏掉关键资料。"""

    retriever = KnowledgeRetriever(db)
    contexts: dict[str, str] = {}
    all_sources: list[str] = []
    all_chunk_ids: list[str] = []
    diagnostics: list[dict[str, object]] = []

    for scene in PROFILE_RETRIEVAL_SCENES:
        query = f"《{document.name}》{scene['query']}"
        version_id = document.active_version_id
        if version_id is None:
            raise KnowledgeDocumentNotFoundError("剧本资源还没有有效版本")
        retrieved = await retriever.retrieve(
            document_id=document.id,
            version_id=version_id,
            store_id=store_id,
            payload=KnowledgeRetrieveRequest(
                query=query,
                top_k=scene["top_k"],
                mode="hybrid",
            ),
        )

        context, sources, chunk_ids = _format_context(retrieved.results)
        key = str(scene["key"])
        contexts[key] = context

        for source in sources:
            if source not in all_sources:
                all_sources.append(source)

        for chunk_id in chunk_ids:
            if chunk_id not in all_chunk_ids:
                all_chunk_ids.append(chunk_id)

        diagnostics.append(
            {
                "key": key,
                "title": scene["title"],
                "hitCount": len(retrieved.results),
                "hasContext": bool(context.strip()),
                "sources": sources[:5],
            }
        )

    return contexts, all_sources, all_chunk_ids, diagnostics


def format_profile_contexts(
    contexts: dict[str, str],
    diagnostics: list[dict[str, object]],
) -> str:
    """把多路召回结果整理成模型更容易理解的分区上下文。"""

    title_map = {
        "basic": "基础信息",
        "roles": "角色信息",
        "relationships": "人物关系",
        "dm_flow": "DM流程",
        "mechanics": "机制规则",
        "truth": "真相结局",
        "materials": "物料线索",
    }

    lines: list[str] = ["# 多路召回结果"]

    lines.append("\n## 资料诊断")
    for item in diagnostics:
        status = "已找到" if item.get("hasContext") else "未找到"
        lines.append(f"- {item.get('title')}: {status}，命中 {item.get('hitCount')} 条")

    for key, title in title_map.items():
        content = contexts.get(key, "").strip()
        if len(content) > MAX_CONTEXT_CHARS_PER_SCENE:
            content = (
                f"{content[:MAX_CONTEXT_CHARS_PER_SCENE]}...\n[本分区内容过长，已截断]"
            )
        lines.append(f"\n## {title}")
        lines.append(content or "未检索到明确资料。")

    return "\n".join(lines)


def extract_role_names(roles: list[dict[str, object]]) -> list[str]:
    """从角色数组里提取角色名，供人物关系专项抽取使用。"""

    names: list[str] = []
    for role in roles:
        value = role.get("name")
        if isinstance(value, str) and value.strip() and value.strip() not in names:
            names.append(value.strip())
    return names


async def extract_script_relationships(
    *,
    document: KnowledgeDocument,
    contexts: dict[str, str],
    draft: ScriptProfileDraft,
) -> ScriptRelationshipsResult:
    """单独抽取人物关系。

    为什么单独做：
    - 基础档案负责“剧本是什么”
    - 人物关系负责“角色之间怎么牵动玩家情绪”
    - 分开后模型更聚焦，也更容易抽到情感线、遗憾线、守护线等剧本杀业务关系
    """

    role_names = extract_role_names(list(draft.roles or []))
    relationships_context = contexts.get("relationships", "")
    roles_context = contexts.get("roles", "")

    return await structured_chat_completion(
        ScriptRelationshipsResult,
        [
            {"role": "system", "content": SCRIPT_RELATIONSHIPS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_relationships_prompt(
                    document_name=document.name,
                    roles_context=roles_context,
                    relationships_context=relationships_context,
                    story_background=draft.story_background,
                    truth_summary=draft.truth_summary,
                    role_names=role_names,
                ),
            },
        ],
        temperature=0.2,
        max_tokens=3000,
    )


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
        relationships=profile.relationships,
        materialChecklist=profile.material_checklist,
        openingRisks=profile.opening_risks,
        spoilerNotes=profile.spoiler_notes,
        sourceChunkIds=profile.source_chunk_ids,
        sources=profile.sources,
        retrievalDiagnostics=profile.retrieval_diagnostics,
        confidenceScore=profile.confidence_score,
        reviewStatus=(
            profile.review_status.value
            if hasattr(profile.review_status, "value")
            else str(profile.review_status)
        ),
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
    document = await _get_script_document(
        db, store_id=store_id, document_id=document_id
    )

    contexts, sources, chunk_ids, diagnostics = await retrieve_profile_contexts(
        db,
        store_id=store_id,
        document=document,
    )

    context = format_profile_contexts(contexts, diagnostics)
    if not any(value.strip() for value in contexts.values()):
        raise ScriptProfileError(
            "当前剧本还没有可用于生成档案的内容，请先完成一键整理给 AI 使用"
        )
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
        max_tokens=4000,
    )

    relationship_result = await extract_script_relationships(
        document=document,
        contexts=contexts,
        draft=draft,
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
    relationships = [
        item.model_dump(mode="json", by_alias=True)
        for item in relationship_result.relationships
    ]
    relationships.sort(
        key=lambda item: (
            int(item.get("displayPriority") or 999),
            -int(item.get("importance") or 0),
            not bool(item.get("isOfficialPair")),
            -int(item.get("confidence") or 0),
        )
    )
    profile.relationships = relationships
    profile.material_checklist = _to_text_list(draft.material_checklist)
    profile.opening_risks = _to_text_list(draft.opening_risks)
    profile.spoiler_notes = _to_text_list(draft.spoiler_notes)
    profile.source_chunk_ids = chunk_ids
    profile.sources = sources
    profile.retrieval_diagnostics = diagnostics
    profile.confidence_score = draft.confidence_score
    missing_scene_titles = [
        str(item["title"]) for item in diagnostics if not item.get("hasContext")
    ]
    review_reasons = [
        *draft.needs_review_reasons,
        *relationship_result.needs_review_reasons,
    ]
    if missing_scene_titles:
        review_reasons.append(
            f"以下资料类型未检索到明确内容：{'、'.join(missing_scene_titles)}"
        )

    profile.review_status = (
        ScriptProfileReviewStatus.NEEDS_REVIEW
        if draft.confidence_score < 75 or review_reasons
        else ScriptProfileReviewStatus.DRAFT
    )
    profile.error_message = "；".join(review_reasons) if review_reasons else None
    await db.flush()
    await db.refresh(profile)
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
    await db.refresh(profile)
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
    await db.refresh(profile)
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
