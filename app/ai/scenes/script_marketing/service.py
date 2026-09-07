"""剧本 AI 运营物料生成服务。

第一版只生成“宣传文案 + 图片生成提示词”草稿，不自动生成图片、不自动发布。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_marketing.models import (
    ScriptMarketingAsset,
    ScriptMarketingAssetStatus,
    ScriptMarketingImageStatus,
)
from app.ai.scenes.script_marketing.prompts import (
    MARKETING_SYSTEM_PROMPT,
    build_marketing_retrieval_query,
    build_marketing_user_prompt,
    format_script_profile_for_marketing,
)
from app.ai.scenes.script_marketing.schemas import (
    ScriptMarketingApproveRequest,
    ScriptMarketingAssetResult,
    ScriptMarketingGenerateImagesRequest,
    ScriptMarketingGenerateRequest,
)
from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.integrations.llm.client import chat_completion, structured_chat_completion
from app.integrations.qwen.image_generation import QwenImageClient
from app.integrations.storage.oss import OssStorage
from app.modules.knowledge.actions.retrieve_chunks import KnowledgeRetriever
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeResourceType
from app.modules.knowledge.schemas import KnowledgeRetrieveRequest
from app.modules.script_profile.models import ScriptProfile


class _MarketingDraft(BaseModel):
    title: str = Field(description="适合场次或宣传页使用的标题")
    summary: str = Field(description="不剧透的一句话/一段简介")
    selling_points: list[str] = Field(description="3-6 个玩家能理解的卖点")
    suitable_players: list[str] = Field(description="适合的人群")
    tags: list[str] = Field(description="适合前端展示的中文短标签，不要英文枚举")
    cover_prompt: str = Field(description="主图生成提示词，不剧透")
    detail_copy: str = Field(description="详情页文案，可直接展示给玩家")
    detail_image_prompts: list[str] = Field(description="2-4 张详情图生成提示词")
    session_form_defaults: dict[str, object] = Field(
        default_factory=dict,
        description="创建场次表单默认值，字段包含 title, description, durationMinutes, capacity, minPlayers, priceYuan, notes",
    )
    risk_notes: list[str] = Field(description="剧透/版权/误导风险提醒")


class ScriptMarketingGenerationError(ApplicationError):
    status_code = 422
    code = "script_marketing_generation_failed"


def _format_context(chunks: list[object]) -> tuple[str, list[str]]:
    lines: list[str] = []
    sources: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        relative_path = getattr(chunk, "relative_path", None) or getattr(
            chunk, "relativePath", ""
        )
        title = getattr(chunk, "title", None) or "未命名片段"
        content = getattr(chunk, "content", "")
        lines.append(f"[{index}] 来源：{relative_path} / {title}\n{content}")
        if relative_path and relative_path not in sources:
            sources.append(relative_path)
    return "\n\n".join(lines), sources


def _safe_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [
            item.strip() for item in value.replace("，", ",").split(",") if item.strip()
        ]
    return fallback


def _extract_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("模型没有返回 JSON 对象")
    return payload


def _draft_from_mapping(
    data: dict[str, object], document: KnowledgeDocument
) -> _MarketingDraft:
    title = str(data.get("title") or f"《{document.name}》沉浸式拼车局").strip()
    summary = str(
        data.get("summary")
        or document.description
        or f"基于《{document.name}》资料生成的玩家可见简介。"
    ).strip()
    selling_points = _safe_list(
        data.get("selling_points") or data.get("sellingPoints"),
        ["沉浸体验", "适合拼车", "门店精选"],
    )
    suitable_players = _safe_list(
        data.get("suitable_players") or data.get("suitablePlayers"),
        ["想体验新剧本的玩家"],
    )
    tags = _safe_list(data.get("tags"), list(document.tags or [])[:4] or ["剧本杀"])
    cover_prompt = str(
        data.get("cover_prompt")
        or data.get("coverPrompt")
        or f"为剧本《{document.name}》生成一张不剧透的宣传主图，突出氛围、场景和类型感。"
    ).strip()
    detail_copy = str(
        data.get("detail_copy") or data.get("detailCopy") or summary
    ).strip()
    detail_image_prompts = _safe_list(
        data.get("detail_image_prompts") or data.get("detailImagePrompts"),
        [cover_prompt],
    )
    risk_notes = _safe_list(
        data.get("risk_notes") or data.get("riskNotes"),
        ["发布前请人工确认不包含凶手、隐藏身份、最终反转等剧透信息"],
    )
    session_form_defaults = (
        data.get("session_form_defaults") or data.get("sessionFormDefaults") or {}
    )
    if not isinstance(session_form_defaults, dict):
        session_form_defaults = {}
    return _MarketingDraft(
        title=title,
        summary=summary,
        selling_points=selling_points,
        suitable_players=suitable_players,
        tags=tags,
        cover_prompt=cover_prompt,
        detail_copy=detail_copy,
        detail_image_prompts=detail_image_prompts,
        session_form_defaults=session_form_defaults,
        risk_notes=risk_notes,
    )


def _asset_to_result(asset: ScriptMarketingAsset) -> ScriptMarketingAssetResult:
    return ScriptMarketingAssetResult(
        documentId=asset.document_id,
        versionId=asset.version_id,
        assetId=asset.id,
        versionNo=asset.version_no,
        status=(
            asset.status.value if hasattr(asset.status, "value") else str(asset.status)
        ),
        managerFeedback=asset.manager_feedback,
        title=asset.title,
        summary=asset.summary,
        sellingPoints=asset.selling_points,
        suitablePlayers=asset.suitable_players,
        tags=asset.tags,
        coverPrompt=asset.cover_prompt,
        coverImageUrl=asset.cover_image_url,
        detailCopy=asset.detail_copy,
        detailImagePrompts=asset.detail_image_prompts,
        detailImageUrls=asset.detail_image_urls,
        sessionFormDefaults=asset.session_form_defaults,
        imageStatus=(
            asset.image_status.value
            if hasattr(asset.image_status, "value")
            else str(asset.image_status)
        ),
        imageErrorMessage=asset.image_error_message,
        riskNotes=asset.risk_notes,
        sources=asset.sources,
        createdAt=asset.created_at,
        approvedAt=asset.approved_at,
    )


def _public_oss_url(object_key: str, storage: OssStorage) -> str:
    """优先返回公共 OSS/CDN 地址；未配置时退回临时预览地址。"""

    if settings.OSS_PUBLIC_BASE_URL:
        return f"{settings.OSS_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
    return storage.presign_get(object_key)


async def _generate_and_store_image(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    image_client: QwenImageClient,
    storage: OssStorage,
    prompt: str,
    filename: str,
) -> tuple[str, str]:
    """生成单张图片并转存到本项目 OSS。"""

    image_bytes = await image_client.generate_one(prompt)
    object_key = f"stores/{store_id}/script-marketing/{asset_id}/images/{filename}"
    await storage.put_bytes(object_key, image_bytes, "image/png")
    return object_key, _public_oss_url(object_key, storage)


async def _generate_draft(
    *,
    document: KnowledgeDocument,
    payload: ScriptMarketingGenerateRequest,
    context: str,
    profile_context: str,
) -> _MarketingDraft:
    messages = [
        {
            "role": "system",
            "content": MARKETING_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": build_marketing_user_prompt(
                document=document,
                payload=payload,
                profile_context=profile_context,
                rag_context=context,
            ),
        },
    ]

    try:
        return await structured_chat_completion(
            _MarketingDraft, messages, temperature=0.4, max_tokens=1800
        )
    except Exception:  # noqa: BLE001 - 结构化输出失败时，需要降级为普通 JSON 输出重试。
        try:
            raw = await chat_completion(
                messages,
                temperature=0.4,
                max_tokens=1800,
                response_format={"type": "json_object"},
            )
        except Exception as error:
            raise ScriptMarketingGenerationError(
                "AI 生成物料失败，请检查模型配置或稍后重试"
            ) from error
        try:
            return _draft_from_mapping(_extract_json_object(raw), document)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as error:
            raise ScriptMarketingGenerationError(
                "AI 生成物料失败，请稍后重试或检查模型 JSON 输出能力"
            ) from error


async def get_best_script_profile(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
) -> ScriptProfile | None:
    """获取当前剧本最可信的剧本档案。

    优先级：
    1. 店长已确认 approved 的档案
    2. 最新生成的档案
    """

    approved_stmt = (
        select(ScriptProfile)
        .where(
            ScriptProfile.store_id == store_id,
            ScriptProfile.document_id == document_id,
            ScriptProfile.review_status == "approved",
        )
        .order_by(ScriptProfile.updated_at.desc())
        .limit(1)
    )
    approved_result = await db.execute(approved_stmt)
    approved_profile = approved_result.scalar_one_or_none()
    if approved_profile is not None:
        return approved_profile

    latest_stmt = (
        select(ScriptProfile)
        .where(
            ScriptProfile.store_id == store_id,
            ScriptProfile.document_id == document_id,
        )
        .order_by(ScriptProfile.updated_at.desc())
        .limit(1)
    )
    latest_result = await db.execute(latest_stmt)
    return latest_result.scalar_one_or_none()


async def generate_script_marketing_assets(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: ScriptMarketingGenerateRequest,
    db: AsyncSession,
) -> ScriptMarketingAssetResult:
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

    profile = await get_best_script_profile(
        db,
        store_id=store_id,
        document_id=document.id,
    )
    profile_context = format_script_profile_for_marketing(profile)

    query = build_marketing_retrieval_query(document, payload)
    retrieved = await KnowledgeRetriever(db).retrieve(
        document_id=document.id,
        version_id=document.active_version_id,
        store_id=store_id,
        payload=KnowledgeRetrieveRequest(query=query, top_k=10, mode="hybrid"),
    )
    context, sources = _format_context(retrieved.results)
    if not context:
        raise KnowledgeDocumentNotFoundError(
            "当前剧本还没有可用于生成物料的 RAG 内容，请先完成文件识别、内容整理和 AI 索引"
        )

    draft = await _generate_draft(
        document=document,
        payload=payload,
        context=context,
        profile_context=profile_context,
    )
    version_no = (
        int(
            await db.scalar(
                select(func.count())
                .select_from(ScriptMarketingAsset)
                .where(
                    ScriptMarketingAsset.store_id == store_id,
                    ScriptMarketingAsset.document_id == document.id,
                )
            )
            or 0
        )
        + 1
    )
    asset = ScriptMarketingAsset(
        id=uuid.uuid4(),
        store_id=store_id,
        document_id=document.id,
        version_id=document.active_version_id,
        version_no=version_no,
        purpose=payload.purpose,
        tone=payload.tone,
        manager_feedback=payload.extra_requirement,
        title=draft.title,
        summary=draft.summary,
        selling_points=draft.selling_points,
        suitable_players=draft.suitable_players,
        tags=draft.tags,
        cover_prompt=draft.cover_prompt,
        detail_copy=draft.detail_copy,
        detail_image_prompts=draft.detail_image_prompts,
        session_form_defaults=draft.session_form_defaults,
        risk_notes=draft.risk_notes,
        sources=sources,
        status=ScriptMarketingAssetStatus.DRAFT,
        created_by_user_id=user_id,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return _asset_to_result(asset)


async def list_script_marketing_assets(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    status: ScriptMarketingAssetStatus | None,
    db: AsyncSession,
) -> list[ScriptMarketingAssetResult]:
    filters = [
        ScriptMarketingAsset.store_id == store_id,
        ScriptMarketingAsset.document_id == document_id,
    ]
    if status is not None:
        filters.append(ScriptMarketingAsset.status == status)
    rows = (
        (
            await db.execute(
                select(ScriptMarketingAsset)
                .where(*filters)
                .order_by(
                    ScriptMarketingAsset.version_no.desc(),
                    ScriptMarketingAsset.created_at.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_asset_to_result(item) for item in rows]


async def approve_script_marketing_asset(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ScriptMarketingApproveRequest,
    db: AsyncSession,
) -> ScriptMarketingAssetResult:
    asset = await db.scalar(
        select(ScriptMarketingAsset).where(
            ScriptMarketingAsset.id == asset_id,
            ScriptMarketingAsset.store_id == store_id,
        )
    )
    if asset is None:
        raise KnowledgeDocumentNotFoundError("AI 运营物料不存在")
    if payload.manager_feedback:
        asset.manager_feedback = payload.manager_feedback
    asset.status = ScriptMarketingAssetStatus.APPROVED
    asset.approved_by_user_id = user_id
    asset.approved_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(asset)
    return _asset_to_result(asset)


async def generate_script_marketing_images(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    payload: ScriptMarketingGenerateImagesRequest,
    db: AsyncSession,
) -> ScriptMarketingAssetResult:
    """为店长已确认的物料生成真实图片，并把图片持久化到 OSS。"""

    asset = await db.scalar(
        select(ScriptMarketingAsset).where(
            ScriptMarketingAsset.id == asset_id,
            ScriptMarketingAsset.store_id == store_id,
        )
    )
    if asset is None:
        raise KnowledgeDocumentNotFoundError("AI 运营物料不存在")
    if asset.status != ScriptMarketingAssetStatus.APPROVED:
        raise ScriptMarketingGenerationError("请先由店长确认物料版本，再生成真实图片")
    if not payload.include_cover and not payload.include_detail:
        raise ScriptMarketingGenerationError("请至少选择生成主图或详情图")

    asset.image_status = ScriptMarketingImageStatus.GENERATING
    asset.image_error_message = None
    await db.flush()

    storage = OssStorage()
    image_client = QwenImageClient()
    cover_key = asset.cover_image_key
    cover_url = asset.cover_image_url
    detail_keys = list(asset.detail_image_keys or [])
    detail_urls = list(asset.detail_image_urls or [])

    try:
        if payload.include_cover:
            cover_key, cover_url = await _generate_and_store_image(
                store_id=store_id,
                asset_id=asset.id,
                image_client=image_client,
                storage=storage,
                prompt=payload.prompt_override or asset.cover_prompt,
                filename="cover.png",
            )
        if payload.include_detail:
            detail_keys = []
            detail_urls = []
            for index, prompt in enumerate(
                (asset.detail_image_prompts or [])[:3], start=1
            ):
                image_key, image_url = await _generate_and_store_image(
                    store_id=store_id,
                    asset_id=asset.id,
                    image_client=image_client,
                    storage=storage,
                    prompt=prompt,
                    filename=f"detail-{index}.png",
                )
                detail_keys.append(image_key)
                detail_urls.append(image_url)
    except Exception as error:
        asset.image_status = ScriptMarketingImageStatus.FAILED
        asset.image_error_message = str(error)
        await db.flush()
        raise

    asset.cover_image_key = cover_key
    asset.cover_image_url = cover_url
    asset.detail_image_keys = detail_keys
    asset.detail_image_urls = detail_urls
    asset.image_status = ScriptMarketingImageStatus.READY
    asset.image_error_message = None
    await db.flush()
    await db.refresh(asset)
    return _asset_to_result(asset)
