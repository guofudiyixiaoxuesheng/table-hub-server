"""剧本 AI 视觉素材生产线服务。

当前阶段先做：
1. 生成剧本视觉档案
2. 管理系统默认视觉风格模板
3. 生成不同用途的图片 Prompt 候选记录

真正调用图片模型、上传 OSS 放到下一阶段。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_visual.models import (
    ScriptVisualAsset,
    ScriptVisualAssetStatus,
    ScriptVisualProfile,
    ScriptVisualProfileStatus,
    VisualStylePreset,
)
from app.ai.scenes.script_visual.prompts import (
    IMAGE_PROMPT_SYSTEM_PROMPT,
    VISUAL_PROFILE_SYSTEM_PROMPT,
    build_image_prompt_prompt,
    build_visual_profile_prompt,
)
from app.ai.scenes.script_visual.schemas import (
    CharacterVisual,
    GenerateScriptVisualAssetRequest,
    GenerateScriptVisualProfileRequest,
    ScriptVisualAssetResult,
    ScriptVisualProfileResult,
    VisualStylePresetResult,
)
from app.core.config import settings
from app.core.exceptions import ApplicationError
from app.integrations.image_generation.client import generate_image
from app.integrations.image_generation.schemas import ImageGenerationRequest
from app.integrations.llm.client import chat_completion, structured_chat_completion
from app.integrations.storage.oss import OssStorage
from app.modules.knowledge.actions.retrieve_chunks import KnowledgeRetriever
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeResourceType
from app.modules.knowledge.schemas import KnowledgeRetrieveRequest
from app.modules.script_profile.models import ScriptProfile


class ScriptVisualError(ApplicationError):
    """视觉生产线通用业务异常。"""

    status_code = 422
    code = "script_visual_error"


class _VisualProfileDraft(BaseModel):
    """LLM 生成的视觉档案草稿。"""

    name: str = Field(description="剧本名称")
    era: str | None = Field(
        default=None, description="时代背景，例如民国上海、现代校园"
    )
    world_setting: str | None = Field(
        default=None, description="世界观/主要空间的视觉描述"
    )
    main_scenes: list[str] = Field(default_factory=list, description="核心场景")
    visual_symbols: list[str] = Field(default_factory=list, description="核心视觉符号")
    color_palette: list[str] = Field(default_factory=list, description="推荐主色调")
    atmosphere_keywords: list[str] = Field(
        default_factory=list, description="氛围关键词"
    )
    character_visuals: list[CharacterVisual] = Field(
        default_factory=list, description="人物公开视觉设定"
    )
    spoiler_safe_rules: list[str] = Field(
        default_factory=list, description="剧透安全规则"
    )
    copyright_safe_rules: list[str] = Field(
        default_factory=list, description="版权安全规则"
    )
    reference_image_urls: list[str] = Field(
        default_factory=list, description="参考图URL"
    )
    confidence_score: int | None = Field(
        default=None, description="视觉档案完整度，0-100"
    )


class _ImagePromptDraft(BaseModel):
    """LLM 生成的最终生图 Prompt 草稿。"""

    prompt: str = Field(description="最终生图 Prompt")
    negative_prompt: str | None = Field(default=None, description="负向提示词")


DEFAULT_STYLE_PRESETS = [
    {
        "name": "民国悬疑电影感",
        "style_type": "cinematic_republic_mystery",
        "description": "适合民国、豪宅、谍战、悬疑、情感纠葛类剧本。",
        "prompt_template": "电影海报质感，民国旧上海美术风格，低饱和深色调，戏剧化光影，胶片颗粒，高级构图，悬疑但不血腥。",
        "negative_prompt": "不要文字、不要logo、不要二维码、不要水印、不要复刻真实海报、不要血腥暴力、不要低清模糊。",
        "recommended_aspect_ratios": ["1:1", "3:4", "9:16"],
        "sort_order": 10,
    },
    {
        "name": "中式恐怖压迫感",
        "style_type": "chinese_horror",
        "description": "适合中式恐怖、民俗、宅院、灵异氛围类剧本。",
        "prompt_template": "中式恐怖氛围，暗红与冷绿光影，老宅、纸灯笼、雾气、阴影留白，压迫感强，克制不血腥。",
        "negative_prompt": "不要过度血腥、不要吓人鬼脸特写、不要文字、不要logo、不要二维码、不要水印。",
        "recommended_aspect_ratios": ["1:1", "3:4", "9:16"],
        "sort_order": 20,
    },
    {
        "name": "欢乐机制综艺感",
        "style_type": "comedy_mechanism",
        "description": "适合欢乐本、机制本、团建活动和轻松拼车宣传。",
        "prompt_template": "明快高饱和配色，轻松综艺感，桌游聚会氛围，夸张但高级的插画风，人物互动活泼。",
        "negative_prompt": "不要恐怖、不要血腥、不要压抑、不要文字、不要logo、不要二维码、不要水印。",
        "recommended_aspect_ratios": ["1:1", "16:9", "3:4"],
        "sort_order": 30,
    },
    {
        "name": "情感沉浸电影感",
        "style_type": "emotional_cinematic",
        "description": "适合情感本、家国本、现代沉浸、细腻关系类剧本。",
        "prompt_template": "电影感情绪海报，柔和光影，克制高级，人物背影或剪影，细腻情绪，留白构图，氛围感强。",
        "negative_prompt": "不要夸张表情、不要廉价网红风、不要文字、不要logo、不要二维码、不要水印。",
        "recommended_aspect_ratios": ["1:1", "3:4", "9:16"],
        "sort_order": 40,
    },
    {
        "name": "古风权谋厚涂感",
        "style_type": "ancient_strategy",
        "description": "适合古风、权谋、宫廷、阵营对抗类剧本。",
        "prompt_template": "古风厚涂插画，宫廷权谋氛围，暗金与墨色，华丽服饰，强构图，肃杀但不血腥。",
        "negative_prompt": "不要现代服饰、不要文字、不要logo、不要二维码、不要水印、不要过度暴露。",
        "recommended_aspect_ratios": ["1:1", "3:4", "9:16"],
        "sort_order": 50,
    },
]


def _safe_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [
            item.strip() for item in value.replace("，", ",").split(",") if item.strip()
        ]
    return []


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


def _format_context(chunks: list[object]) -> str:
    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        relative_path = getattr(chunk, "relative_path", None) or getattr(
            chunk, "relativePath", ""
        )
        title = getattr(chunk, "title", None) or "未命名片段"
        content = getattr(chunk, "content", "")
        lines.append(f"[{index}] 来源：{relative_path} / {title}\n{content}")
    return "\n\n".join(lines)


def _profile_to_result(profile: ScriptVisualProfile) -> ScriptVisualProfileResult:
    return ScriptVisualProfileResult(
        id=profile.id,
        documentId=profile.document_id,
        scriptProfileId=profile.script_profile_id,
        name=profile.name,
        era=profile.era,
        worldSetting=profile.world_setting,
        mainScenes=profile.main_scenes,
        visualSymbols=profile.visual_symbols,
        colorPalette=profile.color_palette,
        atmosphereKeywords=profile.atmosphere_keywords,
        characterVisuals=profile.character_visuals,
        spoilerSafeRules=profile.spoiler_safe_rules,
        copyrightSafeRules=profile.copyright_safe_rules,
        referenceImageUrls=profile.reference_image_urls,
        confidenceScore=profile.confidence_score,
        status=profile.status,
        errorMessage=profile.error_message,
        createdAt=profile.created_at,
        updatedAt=profile.updated_at,
        approvedAt=profile.approved_at,
    )


def _style_to_result(style: VisualStylePreset) -> VisualStylePresetResult:
    return VisualStylePresetResult(
        id=style.id,
        name=style.name,
        styleType=style.style_type,
        description=style.description,
        promptTemplate=style.prompt_template,
        negativePrompt=style.negative_prompt,
        recommendedAspectRatios=style.recommended_aspect_ratios,
        isSystem=style.is_system,
        isActive=style.is_active,
        sortOrder=style.sort_order,
    )


def _asset_to_result(asset: ScriptVisualAsset) -> ScriptVisualAssetResult:
    return ScriptVisualAssetResult(
        id=asset.id,
        documentId=asset.document_id,
        visualProfileId=asset.visual_profile_id,
        stylePresetId=asset.style_preset_id,
        usageType=asset.usage_type,
        usageLabel=asset.usage_label,
        prompt=asset.prompt,
        negativePrompt=asset.negative_prompt,
        aspectRatio=asset.aspect_ratio,
        objectKey=asset.object_key,
        imageUrl=asset.image_url,
        status=asset.status,
        errorMessage=asset.error_message,
        isSelected=asset.is_selected,
        selectedAt=asset.selected_at,
        createdAt=asset.created_at,
        updatedAt=asset.updated_at,
    )


def _public_oss_url(object_key: str, storage: OssStorage) -> str:
    """优先返回公共 OSS/CDN 地址；未配置时退回临时预览地址。"""

    if settings.OSS_PUBLIC_BASE_URL:
        return f"{settings.OSS_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
    return storage.presign_get(object_key)


def _draft_from_mapping(
    data: dict[str, object], document: KnowledgeDocument
) -> _VisualProfileDraft:
    character_visuals_raw = (
        data.get("character_visuals") or data.get("characterVisuals") or []
    )
    character_visuals: list[CharacterVisual] = []
    if isinstance(character_visuals_raw, list):
        for item in character_visuals_raw:
            if isinstance(item, dict) and item.get("name"):
                try:
                    character_visuals.append(CharacterVisual.model_validate(item))
                except ValidationError:
                    continue

    return _VisualProfileDraft(
        name=str(data.get("name") or document.name),
        era=str(data.get("era") or "") or None,
        world_setting=str(data.get("world_setting") or data.get("worldSetting") or "")
        or None,
        main_scenes=_safe_list(data.get("main_scenes") or data.get("mainScenes")),
        visual_symbols=_safe_list(
            data.get("visual_symbols") or data.get("visualSymbols")
        ),
        color_palette=_safe_list(data.get("color_palette") or data.get("colorPalette")),
        atmosphere_keywords=_safe_list(
            data.get("atmosphere_keywords") or data.get("atmosphereKeywords")
        ),
        character_visuals=character_visuals,
        spoiler_safe_rules=_safe_list(
            data.get("spoiler_safe_rules") or data.get("spoilerSafeRules")
        ),
        copyright_safe_rules=_safe_list(
            data.get("copyright_safe_rules") or data.get("copyrightSafeRules")
        ),
        reference_image_urls=_safe_list(
            data.get("reference_image_urls") or data.get("referenceImageUrls")
        ),
        confidence_score=int(
            data.get("confidence_score") or data.get("confidenceScore") or 60
        ),
    )


def _image_prompt_from_mapping(data: dict[str, object]) -> _ImagePromptDraft:
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        raise TypeError("模型没有返回 prompt")
    negative_prompt = str(
        data.get("negative_prompt") or data.get("negativePrompt") or ""
    ).strip()
    return _ImagePromptDraft(
        prompt=prompt,
        negative_prompt=negative_prompt or None,
    )


def _visual_profile_to_prompt_context(profile: ScriptVisualProfile) -> str:
    """把视觉档案压缩成生图 Prompt 可用的上下文。"""

    return f"""
剧本名称：{profile.name}
时代背景：{profile.era or "暂无"}
世界观/主要空间：{profile.world_setting or "暂无"}
核心场景：{", ".join(profile.main_scenes or []) or "暂无"}
视觉符号：{", ".join(profile.visual_symbols or []) or "暂无"}
推荐色调：{", ".join(profile.color_palette or []) or "暂无"}
氛围关键词：{", ".join(profile.atmosphere_keywords or []) or "暂无"}
人物公开视觉：{profile.character_visuals or "暂无"}
剧透安全规则：{", ".join(profile.spoiler_safe_rules or []) or "暂无"}
版权安全规则：{", ".join(profile.copyright_safe_rules or []) or "暂无"}
参考图：{", ".join(profile.reference_image_urls or []) or "暂无"}
""".strip()


async def get_best_script_profile(
    db: AsyncSession,
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
) -> ScriptProfile | None:
    """获取最可信的剧本档案：优先店长确认版，否则取最新版。"""

    approved = await db.scalar(
        select(ScriptProfile)
        .where(
            ScriptProfile.store_id == store_id,
            ScriptProfile.document_id == document_id,
            ScriptProfile.review_status == "approved",
            ScriptProfile.deleted_at.is_(None),
        )
        .order_by(ScriptProfile.updated_at.desc())
        .limit(1)
    )
    if approved is not None:
        return approved

    return await db.scalar(
        select(ScriptProfile)
        .where(
            ScriptProfile.store_id == store_id,
            ScriptProfile.document_id == document_id,
            ScriptProfile.deleted_at.is_(None),
        )
        .order_by(ScriptProfile.updated_at.desc())
        .limit(1)
    )


async def ensure_default_style_presets(db: AsyncSession) -> None:
    """确保系统默认视觉风格模板存在。

    这里用 name + store_id=null 作为简单幂等条件。
    """

    existing_names = set(
        (
            await db.execute(
                select(VisualStylePreset.name).where(
                    VisualStylePreset.store_id.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for item in DEFAULT_STYLE_PRESETS:
        if item["name"] in existing_names:
            continue
        db.add(
            VisualStylePreset(
                id=uuid.uuid4(),
                store_id=None,
                name=item["name"],
                style_type=item["style_type"],
                description=item["description"],
                prompt_template=item["prompt_template"],
                negative_prompt=item["negative_prompt"],
                recommended_aspect_ratios=item["recommended_aspect_ratios"],
                is_system=True,
                is_active=True,
                sort_order=item["sort_order"],
            )
        )
    await db.flush()


async def list_visual_style_presets(
    *,
    store_id: uuid.UUID,
    db: AsyncSession,
) -> list[VisualStylePresetResult]:
    """查询可用视觉风格模板：系统模板 + 当前门店自定义模板。"""

    await ensure_default_style_presets(db)
    rows = (
        (
            await db.execute(
                select(VisualStylePreset)
                .where(
                    VisualStylePreset.is_active.is_(True),
                    or_(
                        VisualStylePreset.store_id.is_(None),
                        VisualStylePreset.store_id == store_id,
                    ),
                )
                .order_by(
                    VisualStylePreset.sort_order.asc(),
                    VisualStylePreset.created_at.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_style_to_result(item) for item in rows]


async def get_script_visual_profile(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession,
) -> ScriptVisualProfileResult | None:
    """查询某个剧本最新视觉档案。"""

    profile = await db.scalar(
        select(ScriptVisualProfile)
        .where(
            ScriptVisualProfile.store_id == store_id,
            ScriptVisualProfile.document_id == document_id,
        )
        .order_by(ScriptVisualProfile.updated_at.desc())
        .limit(1)
    )
    return _profile_to_result(profile) if profile else None


async def generate_script_visual_profile(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: GenerateScriptVisualProfileRequest,
    db: AsyncSession,
) -> ScriptVisualProfileResult:
    """基于剧本档案 + RAG 生成视觉档案。"""

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

    script_profile = await get_best_script_profile(
        db,
        store_id=store_id,
        document_id=document.id,
    )

    retrieved = await KnowledgeRetriever(db).retrieve(
        document_id=document.id,
        version_id=document.active_version_id,
        store_id=store_id,
        payload=KnowledgeRetrieveRequest(
            query=(
                f"为剧本《{document.name}》提炼视觉风格。重点查找时代背景、核心场景、"
                "人物公开身份与服装、道具、色彩、氛围、宣传安全边界。"
            ),
            top_k=12,
            mode="hybrid",
        ),
    )
    rag_context = _format_context(retrieved.results)
    if not rag_context:
        raise ScriptVisualError(
            "当前剧本缺少可用于提炼视觉档案的 RAG 内容，请先完成内容整理和 AI 索引"
        )

    messages = [
        {"role": "system", "content": VISUAL_PROFILE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_visual_profile_prompt(
                document=document,
                profile=script_profile,
                rag_context=rag_context,
                reference_image_urls=payload.reference_image_urls,
                extra_requirement=payload.extra_requirement,
            ),
        },
    ]

    try:
        draft = await structured_chat_completion(
            _VisualProfileDraft,
            messages,
            temperature=0.25,
            max_tokens=1800,
        )
    except Exception:  # noqa: BLE001 - 结构化输出失败时降级为普通 JSON 输出。
        try:
            raw = await chat_completion(
                messages,
                temperature=0.25,
                max_tokens=1800,
                response_format={"type": "json_object"},
            )
            draft = _draft_from_mapping(_extract_json_object(raw), document)
        except Exception as error:
            raise ScriptVisualError(
                "AI 视觉档案生成失败，请稍后重试或检查模型配置"
            ) from error

    profile = ScriptVisualProfile(
        id=uuid.uuid4(),
        store_id=store_id,
        document_id=document.id,
        script_profile_id=script_profile.id if script_profile else None,
        name=draft.name or document.name,
        era=draft.era,
        world_setting=draft.world_setting,
        main_scenes=draft.main_scenes,
        visual_symbols=draft.visual_symbols,
        color_palette=draft.color_palette,
        atmosphere_keywords=draft.atmosphere_keywords,
        character_visuals=[
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in draft.character_visuals
        ],
        spoiler_safe_rules=draft.spoiler_safe_rules,
        copyright_safe_rules=draft.copyright_safe_rules,
        reference_image_urls=payload.reference_image_urls or draft.reference_image_urls,
        confidence_score=draft.confidence_score,
        status=ScriptVisualProfileStatus.READY.value,
        created_by_user_id=user_id,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    return _profile_to_result(profile)


async def list_script_visual_assets(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession,
    usage_type: str | None = None,
) -> list[ScriptVisualAssetResult]:
    """查询某个剧本的视觉素材候选记录。"""

    conditions = [
        ScriptVisualAsset.store_id == store_id,
        ScriptVisualAsset.document_id == document_id,
    ]
    if usage_type:
        conditions.append(ScriptVisualAsset.usage_type == usage_type)

    rows = (
        (
            await db.execute(
                select(ScriptVisualAsset)
                .where(*conditions)
                .order_by(
                    ScriptVisualAsset.is_selected.desc(),
                    ScriptVisualAsset.created_at.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return [_asset_to_result(item) for item in rows]


async def generate_script_visual_assets(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload: GenerateScriptVisualAssetRequest,
    db: AsyncSession,
) -> list[ScriptVisualAssetResult]:
    """生成视觉素材候选记录。

    现阶段先生成“可直接交给图片模型的 Prompt”，并落库。
    下一阶段把 image_url/object_key 回填即可，不需要改前端数据结构。
    """

    document = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocument.resource_type == KnowledgeResourceType.SCRIPT,
        )
    )
    if document is None:
        raise KnowledgeDocumentNotFoundError("剧本资源不存在")

    profile_conditions = [
        ScriptVisualProfile.store_id == store_id,
        ScriptVisualProfile.document_id == document_id,
    ]
    if payload.visual_profile_id:
        profile_conditions.append(ScriptVisualProfile.id == payload.visual_profile_id)

    visual_profile = await db.scalar(
        select(ScriptVisualProfile)
        .where(*profile_conditions)
        .order_by(
            ScriptVisualProfile.status.desc(),
            ScriptVisualProfile.updated_at.desc(),
        )
        .limit(1)
    )
    if visual_profile is None:
        raise ScriptVisualError("请先生成剧本视觉档案，再生成视觉素材")

    style_conditions = [VisualStylePreset.is_active.is_(True)]
    if payload.style_preset_id:
        style_conditions.append(VisualStylePreset.id == payload.style_preset_id)
    else:
        style_conditions.append(
            or_(
                VisualStylePreset.store_id.is_(None),
                VisualStylePreset.store_id == store_id,
            )
        )

    await ensure_default_style_presets(db)
    style = await db.scalar(
        select(VisualStylePreset)
        .where(*style_conditions)
        .order_by(
            VisualStylePreset.sort_order.asc(), VisualStylePreset.created_at.asc()
        )
        .limit(1)
    )
    if style is None:
        raise ScriptVisualError("视觉风格模板不存在或已停用")

    results: list[ScriptVisualAssetResult] = []
    for _ in range(payload.count):
        messages = [
            {"role": "system", "content": IMAGE_PROMPT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_image_prompt_prompt(
                    visual_profile=_visual_profile_to_prompt_context(visual_profile),
                    style_preset_name=style.name,
                    style_prompt_template=style.prompt_template,
                    negative_prompt=style.negative_prompt,
                    usage_type=payload.usage_type,
                    usage_label=payload.usage_label,
                    aspect_ratio=payload.aspect_ratio,
                    extra_requirement=payload.extra_requirement,
                ),
            },
        ]
        try:
            draft = await structured_chat_completion(
                _ImagePromptDraft,
                messages,
                temperature=0.45,
                max_tokens=1000,
            )
        except Exception:  # noqa: BLE001 - 结构化失败时降级 JSON 解析。
            try:
                raw = await chat_completion(
                    messages,
                    temperature=0.45,
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                )
                draft = _image_prompt_from_mapping(_extract_json_object(raw))
            except Exception as error:
                raise ScriptVisualError(
                    "AI 图片 Prompt 生成失败，请稍后重试"
                ) from error

        asset = ScriptVisualAsset(
            id=uuid.uuid4(),
            store_id=store_id,
            document_id=document.id,
            visual_profile_id=visual_profile.id,
            style_preset_id=style.id,
            usage_type=payload.usage_type,
            usage_label=payload.usage_label,
            prompt=draft.prompt,
            negative_prompt=draft.negative_prompt or style.negative_prompt,
            aspect_ratio=payload.aspect_ratio,
            status=ScriptVisualAssetStatus.DRAFT.value,
            created_by_user_id=user_id,
        )
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        results.append(_asset_to_result(asset))

    return results


async def select_script_visual_asset(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: AsyncSession,
) -> ScriptVisualAssetResult:
    """把某张候选图选为当前用途的正式素材。"""

    asset = await db.scalar(
        select(ScriptVisualAsset).where(
            ScriptVisualAsset.id == asset_id,
            ScriptVisualAsset.store_id == store_id,
        )
    )
    if asset is None:
        raise ScriptVisualError("视觉素材不存在")

    siblings = (
        (
            await db.execute(
                select(ScriptVisualAsset).where(
                    ScriptVisualAsset.store_id == store_id,
                    ScriptVisualAsset.document_id == asset.document_id,
                    ScriptVisualAsset.usage_type == asset.usage_type,
                    ScriptVisualAsset.id != asset.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for item in siblings:
        item.is_selected = False
        if item.status == ScriptVisualAssetStatus.SELECTED.value:
            item.status = ScriptVisualAssetStatus.READY.value
        item.selected_at = None

    asset.is_selected = True
    asset.status = ScriptVisualAssetStatus.SELECTED.value
    asset.selected_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(asset)
    return _asset_to_result(asset)


async def delete_script_visual_asset(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """删除一条视觉候选素材记录。"""

    asset = await db.scalar(
        select(ScriptVisualAsset).where(
            ScriptVisualAsset.id == asset_id,
            ScriptVisualAsset.store_id == store_id,
        )
    )
    if asset is None:
        raise ScriptVisualError("视觉素材不存在")

    await db.delete(asset)
    await db.flush()


async def approve_script_visual_profile(
    *,
    store_id: uuid.UUID,
    profile_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ScriptVisualProfileResult:
    """店长确认视觉档案可用。"""

    profile = await db.scalar(
        select(ScriptVisualProfile).where(
            ScriptVisualProfile.id == profile_id,
            ScriptVisualProfile.store_id == store_id,
        )
    )
    if profile is None:
        raise ScriptVisualError("视觉档案不存在")

    profile.status = ScriptVisualProfileStatus.APPROVED.value
    profile.approved_by_user_id = user_id
    profile.approved_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(profile)
    return _profile_to_result(profile)


async def generate_script_visual_asset_image(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: AsyncSession,
) -> ScriptVisualAssetResult:
    """根据视觉素材 Prompt 生成真实图片。

    当前只负责业务闭环：
    - 查询候选素材
    - 调用统一图片生成器
    - 回填图片 URL / OSS key / 状态

    具体接哪个图片模型，由 app.integrations.image_generation.client 决定。
    """

    asset = await db.scalar(
        select(ScriptVisualAsset).where(
            ScriptVisualAsset.id == asset_id,
            ScriptVisualAsset.store_id == store_id,
        )
    )
    if asset is None:
        raise ScriptVisualError("视觉素材不存在")

    asset.status = ScriptVisualAssetStatus.DRAFT.value
    asset.error_message = None
    await db.flush()

    try:
        result = await generate_image(
            ImageGenerationRequest(
                prompt=asset.prompt,
                negative_prompt=asset.negative_prompt,
                aspect_ratio=asset.aspect_ratio,
            )
        )
    except NotImplementedError as error:
        asset.status = ScriptVisualAssetStatus.FAILED.value
        asset.error_message = "图片生成服务暂未接入，请先配置图片模型供应商"
        await db.flush()
        await db.refresh(asset)
        raise ScriptVisualError(asset.error_message) from error
    except Exception as error:
        asset.status = ScriptVisualAssetStatus.FAILED.value
        asset.error_message = "图片生成失败，请稍后重试"
        await db.flush()
        await db.refresh(asset)
        raise ScriptVisualError(asset.error_message) from error

    if not result.image_url and not result.image_bytes:
        asset.status = ScriptVisualAssetStatus.FAILED.value
        asset.error_message = "图片生成服务没有返回图片"
        await db.flush()
        await db.refresh(asset)
        raise ScriptVisualError(asset.error_message)

    if result.image_bytes:
        object_key = (
            f"stores/{store_id}/script-visual/{asset.document_id}/"
            f"assets/{asset.id}/{asset.usage_type}.png"
        )
        storage = OssStorage()
        await storage.put_bytes(object_key, result.image_bytes, "image/png")
        asset.object_key = object_key
        asset.image_url = _public_oss_url(object_key, storage)
    else:
        asset.image_url = result.image_url

    asset.status = ScriptVisualAssetStatus.READY.value
    await db.flush()
    await db.refresh(asset)
    return _asset_to_result(asset)
