"""剧本 AI 运营物料生成服务。

第一版只生成“宣传文案 + 图片生成提示词”草稿，不自动生成图片、不自动发布。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.script_art_reference.models import ScriptArtReferenceStyleProfile
from app.ai.scenes.script_marketing.models import (
    ScriptMarketingAsset,
    ScriptMarketingAssetStatus,
    ScriptMarketingImage,
    ScriptMarketingImageStatus,
)
from app.ai.scenes.script_marketing.prompts import (
    MARKETING_SYSTEM_PROMPT,
    build_marketing_retrieval_query,
    build_marketing_user_prompt,
    format_script_profile_for_marketing,
)
from app.ai.scenes.script_marketing.schemas import (
    MarketingMoments,
    MarketingPlayerCard,
    MarketingPlayerDetail,
    MarketingSessionFormDefaults,
    ScriptMarketingApproveRequest,
    ScriptMarketingAssetResult,
    ScriptMarketingGenerateImagesRequest,
    ScriptMarketingGenerateRequest,
    ScriptMarketingImageResult,
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

logger = logging.getLogger(__name__)


class _MarketingDraft(BaseModel):
    usage_type: str = Field(
        default="session_recruiting",
        description="物料用途类型，例如 session_recruiting、moments、newbie、holiday、custom",
    )
    usage_label: str = Field(default="拼车招募版", description="物料用途中文名称")
    title: str = Field(description="适合场次或宣传页使用的标题")
    summary: str = Field(description="不剧透的一句话/一段简介")
    selling_points: list[str] = Field(description="3-6 个玩家能理解的卖点")
    suitable_players: list[str] = Field(description="适合的人群")
    tags: list[str] = Field(description="适合前端展示的中文短标签，不要英文枚举")
    cover_prompt: str = Field(
        description=(
            "主图创意简报，不剧透。必须先写标题视觉命题：把剧本标题翻译为一场可见的"
            "公开冲突、一个主视觉锚点和一个象征物；标题语义优先级高于泛泛的场景氛围。"
            "再根据可信资料给出发生中的具体场景事件，以及 2-5 名角色的公开身份、衣着、"
            "表情或动作；资料不足时明确用非特指角色，不得编造设定。"
        )
    )
    detail_copy: str = Field(description="详情页文案，可直接展示给玩家")
    detail_image_prompts: list[str] = Field(description="2-4 张详情图生成提示词")
    session_form_defaults: MarketingSessionFormDefaults = Field(
        default_factory=MarketingSessionFormDefaults,
        description="创建场次表单默认值，字段包含 title, description, durationMinutes, capacity, minPlayers, priceYuan, notes",
    )
    player_card: MarketingPlayerCard = Field(
        default_factory=MarketingPlayerCard,
        description="玩家端拼车列表卡片物料",
    )
    player_detail: MarketingPlayerDetail = Field(
        default_factory=MarketingPlayerDetail,
        description="玩家端详情页物料",
    )
    moments: MarketingMoments = Field(
        default_factory=MarketingMoments,
        description="朋友圈传播文案和朋友圈海报提示词",
    )
    risk_notes: list[str] = Field(description="剧透/版权/误导风险提醒")


class _ImageVisualDirection(BaseModel):
    """供文生图使用的短导演简报，不让图像模型自行消化整份剧本资料。"""

    scene_event: str = Field(description="一个正在发生的公开戏剧事件，60 字以内")
    visual_anchor: str = Field(description="单一主视觉锚点，30 字以内")
    environment_details: str = Field(
        description="与公开设定一致的空间、时代、陈设和景深细节，100 字以内"
    )
    primary_subject: str = Field(description="主体人物或主体动作，40 字以内")
    supporting_characters: list[str] = Field(
        default_factory=list, description="最多 3 名配角及其动作"
    )
    party_or_genre_signals: list[str] = Field(
        default_factory=list, description="最多 3 个一眼可见的题材信号"
    )
    visual_metaphor: str = Field(description="一个不含文字的原创象征物，30 字以内")
    facial_expression_and_gesture: str = Field(
        description="主体及配角的表情、手势和视线关系，80 字以内"
    )
    avoid: list[str] = Field(default_factory=list, description="最多 4 项画面禁止项")


class ScriptMarketingGenerationError(ApplicationError):
    status_code = 422
    code = "script_marketing_generation_failed"


def _anonymize_role_names(text: str, role_names: list[str]) -> str:
    """用角色编号替换剧本专名，降低上下游模型的 IP 误判风险。"""

    aliases: dict[str, str] = {}
    for index, name in enumerate(
        dict.fromkeys(name.strip() for name in role_names if name.strip()), start=1
    ):
        for variant in (name, *name.replace("·", " ").split()):
            if len(variant) >= 2:
                aliases.setdefault(variant, f"角色{index}")

    sanitized = text
    for name, alias in sorted(
        aliases.items(), key=lambda item: len(item[0]), reverse=True
    ):
        sanitized = sanitized.replace(name, alias)
    # 背景或简介里还可能出现不在角色表中的人物全名，例如活动主办人。
    return re.sub(
        r"[\u4e00-\u9fff]{1,8}[·・][\u4e00-\u9fff]{1,12}", "某位角色", sanitized
    )


def _sanitize_for_image_provider(text: str, role_names: list[str]) -> str:
    """生图模型只接收画面语义，不接收剧本标题或任何角色专名。"""

    sanitized = _anonymize_role_names(text, role_names)
    sanitized = re.sub(r"《[^》]{1,80}》", "当前剧本", sanitized)
    return sanitized.replace("IP", "已有内容")


async def _distill_image_visual_direction(
    *,
    asset: ScriptMarketingAsset,
    base_prompt: str,
    script_visual_context: str,
    script_role_names: list[str],
) -> _ImageVisualDirection:
    """把长资料收敛成一张图可执行的导演简报。"""

    safe_base = _sanitize_for_image_provider(base_prompt, script_role_names)
    safe_context = _sanitize_for_image_provider(
        script_visual_context, script_role_names
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是面向年轻剧本杀玩家的商业海报创意总监。把输入资料收敛为一张图的短导演简报。"
                "只保留一个正在发生的公开事件和一个视觉锚点；配角最多三人，不能排列站立或做人物档案群像。"
                "若资料包含派对、晚宴、庆祝或社交聚会，必须用可见动作和道具表现其正在发生，而非空场景。"
                "不生成画面内文字，不复述剧本标题或任何人物专名，不使用真实品牌、现成角色、凶手、尸体、案件答案或剧透。"
                "人物的职业、关系和情绪只能转译为服装、动作与表情。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"公开简介：{_sanitize_for_image_provider(asset.summary, script_role_names)}\n"
                f"标签：{'、'.join(str(tag) for tag in (asset.tags or [])[:6])}\n"
                f"已确认的公开设定：{safe_context[:1800]}\n"
                f"原始创意素材：{safe_base[:2200]}"
            ),
        },
    ]
    try:
        direction = await structured_chat_completion(
            _ImageVisualDirection, messages, temperature=0.25, max_tokens=520
        )
    except Exception as error:  # noqa: BLE001 - 生图不应因导演简报失败而无法继续。
        logger.warning("image visual direction fallback: %s", error)
        return _ImageVisualDirection(
            scene_event="一场公开社交聚会在突发异常中骤然凝固，现场人物的动作被打断。",
            visual_anchor="正在倾倒的酒杯与延伸的光影",
            environment_details="现代公寓客厅，派对长桌、落地窗夜景与半开门形成前中后景。",
            primary_subject="前景一位年轻成年人停在未完成的动作中，回望异常来源。",
            supporting_characters=["两位配角以交错景深呈现惊讶和防备"],
            party_or_genre_signals=["派对桌面", "散落邀请卡", "暖色串灯"],
            visual_metaphor="冷暖交界的门缝光线",
            facial_expression_and_gesture="主体屏住呼吸，手停在半空；配角惊讶回望，彼此视线交错。",
            avoid=["静态排队群像", "画面文字", "剧透场景"],
        )

    return _ImageVisualDirection(
        scene_event=_sanitize_for_image_provider(
            direction.scene_event, script_role_names
        )[:120],
        visual_anchor=_sanitize_for_image_provider(
            direction.visual_anchor, script_role_names
        )[:80],
        environment_details=_sanitize_for_image_provider(
            direction.environment_details, script_role_names
        )[:220],
        primary_subject=_sanitize_for_image_provider(
            direction.primary_subject, script_role_names
        )[:120],
        supporting_characters=[
            _sanitize_for_image_provider(item, script_role_names)[:100]
            for item in direction.supporting_characters[:3]
        ],
        party_or_genre_signals=[
            _sanitize_for_image_provider(item, script_role_names)[:60]
            for item in direction.party_or_genre_signals[:3]
        ],
        visual_metaphor=_sanitize_for_image_provider(
            direction.visual_metaphor, script_role_names
        )[:80],
        facial_expression_and_gesture=_sanitize_for_image_provider(
            direction.facial_expression_and_gesture, script_role_names
        )[:180],
        avoid=[
            _sanitize_for_image_provider(item, script_role_names)[:60]
            for item in direction.avoid[:4]
        ],
    )


async def _apply_art_style_profile(
    *,
    store_id: uuid.UUID,
    profile_id: uuid.UUID | None,
    base_prompt: str,
    asset: ScriptMarketingAsset,
    script_visual_context: str,
    script_role_names: list[str],
    db: AsyncSession,
) -> str:
    """把“画面摘要”编译为可直接发送给生图模型的生产级 Prompt。

    上游 LLM 生成的 ``cover_prompt`` 只负责表达创意意图，通常不足以稳定控制
    生图结果。这里不再把它原样透传：无论有没有选视觉规律档案，都会补齐叙事、
    构图、媒介、光影、留白和负面约束；档案只负责替换其中的风格规律。
    """

    def as_sentence_list(value: object, *, limit: int) -> str:
        if isinstance(value, list):
            values = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, str) and value.strip():
            values = [value.strip()]
        else:
            values = []
        return "；".join(values[:limit])

    # 生图服务会把某些剧本角色名识别成既有影视/小说 IP（例如角色名恰好与
    # 知名作品重名）。档案本身可以保留原始资料供店内管理，但最终送往生图模型的
    # 指令只需要角色的公开职业、关系与行为，因此统一改为中性编号。
    profile: ScriptArtReferenceStyleProfile | None = None
    if profile_id is not None:
        profile = await db.scalar(
            select(ScriptArtReferenceStyleProfile).where(
                ScriptArtReferenceStyleProfile.id == profile_id,
                ScriptArtReferenceStyleProfile.store_id == store_id,
                ScriptArtReferenceStyleProfile.status == "ready",
            )
        )
        if profile is None:
            raise ScriptMarketingGenerationError(
                "所选视觉规律档案不存在、不可用，或不属于当前门店"
            )

    analysis = (
        profile.analysis_json
        if profile and isinstance(profile.analysis_json, dict)
        else {}
    )
    style_summary = str(
        analysis.get("styleSummary")
        or "电影感商业插画海报，具备明确的手绘概括与印刷质感"
    )
    composition = as_sentence_list(analysis.get("compositionRules"), limit=5)
    colors = as_sentence_list(analysis.get("colorAndLighting"), limit=5)
    print_texture = as_sentence_list(analysis.get("printTextureRules"), limit=5)
    tags = "、".join(
        str(tag).strip() for tag in (asset.tags or [])[:6] if str(tag).strip()
    )
    profile_name = profile.name if profile else "通用商业海报视觉规则"
    negative_prompt = (profile.negative_prompt or "").strip() if profile else ""
    direction = await _distill_image_visual_direction(
        asset=asset,
        base_prompt=base_prompt,
        script_visual_context=script_visual_context,
        script_role_names=script_role_names,
    )

    # 万相不是策划模型：它只接收短、无冲突、镜头化的最终指令。剧本档案、完整
    # 角色资料和原始创意已由上面的导演简报消化，不能再原样塞给它。
    return "\n".join(
        [
            "原创商业插画海报，竖版 9:16，面向年轻剧本杀玩家；无文字、无数字、无 Logo、无水印。",
            f"正在发生的戏剧瞬间：{direction.scene_event}",
            f"唯一视觉锚点：{direction.visual_anchor}。",
            f"空间与景深：{direction.environment_details}。",
            f"主体动作：{direction.primary_subject}。",
            f"配角最多三人，按前景、中景、远景交错：{'；'.join(direction.supporting_characters) or '仅用失焦配角烘托主体'}。",
            f"表情、手势与视线关系：{direction.facial_expression_and_gesture}。",
            f"必须清晰可见：{'、'.join(direction.party_or_genre_signals) or '公开故事中的核心场景信号'}。",
            f"克制的视觉隐喻：{direction.visual_metaphor}。",
            "非对称竖版电影海报构图，主体占画面约 45%，以桌面、门缝或光束引导视线；画面必须从顶边到四周完整铺满，不留白边、不留大块空白。若需后期排版区，仅在画面底部或侧边保留不超过 12% 的低信息区域。",
            f"当代青年商业插画与独立杂志编辑海报感：{style_summary[:260]}。",
            f"构图规律：{composition[:260] or '前中后景清晰，避免平均铺满画面'}。",
            f"色彩与光影：{colors[:260] or '三至四色，主体对比最高，背景降噪'}。",
            f"印刷材质：{print_texture[:220] or '哑光未涂布纸纤维、局部网点、干刷边缘和轻微套色不齐；主体依然清晰'}。",
            "禁止静态排队群像、人物正面合照、所有角色完整入镜、空走廊、空办公室、摄影棚质感、丝滑 3D、可读文字、品牌标识、已有角色特征、尸体或案件答案。",
            f"额外避免：{'、'.join(direction.avoid)}。",
        ]
    )

    # 使用分段而非一长段散文：当前接入的大多数生图模型都能更稳定地理解这种层级。
    return "\n".join(
        [
            "【任务】",
            f"为当前剧本杀运营物料制作一张竖版{asset.usage_label}主视觉。原创商业海报插画，使用独立设计的角色、场景与版式，不出现品牌、现成角色、标题字或 Logo。",
            "",
            "【剧本语境】",
            f"玩家可见简介：{_sanitize_for_image_provider(asset.summary, script_role_names)}",
            f"类型/情绪关键词：{tags or '以物料内容呈现的类型氛围为准'}。",
            "必须只传达可公开的氛围、冲突与期待感；不得表现凶手、真相、隐藏身份、最终反转或任何剧透信息。",
            "",
            "【目标受众与当代审美】",
            (
                "目标受众是 18-30 岁年轻剧本杀玩家。画面须具备当代青年商业插画、独立杂志编辑海报的利落感和视觉能量；"
                "粗粝感只来自印刷材质，不得变成陈旧、暮气或古董收藏品风格。"
            ),
            (
                "若当前剧本资料没有明确的年代、地域或角色年龄，默认使用现代社交/职场语境与 20-35 岁成年人；"
                "不得擅自使用维多利亚古宅、复古绅士装、老年面孔、泛黄棕褐滤镜或厚重怀旧陈设。"
                "如果资料明确指定年代或年龄，应尊重设定，但用年轻、时髦、具有当代传播力的视觉转译呈现。"
            ),
            "",
            "【剧本档案视觉设定：优先于默认审美】",
            script_visual_context,
            (
                "严格遵循此处明确的年代、地域、建筑、社会环境与角色公开身份。只有该设定缺失或无法确认时，"
                "才使用现代青年职场/社交语境作为默认值；年轻化指传播设计、节奏、人物精神面貌和审美表达，"
                "不意味着抹掉古堡、民国、古风、历史或奇幻等已确认世界观。"
            ),
            "",
            "【核心画面叙事】",
            "【标题视觉命题：最高优先级】",
            "当前剧本标题已经在上游转译为视觉命题。先把该命题落实为一个正在发生的公开冲突、一个必须看见的主视觉锚点、以及一个贯穿画面的象征物；观众即使看不到标题文字，也应能从画面立刻感到其核心含义。",
            "标题命题的权重高于泛化的‘悬疑办公室’或‘氛围感’：所有人物、场景、道具、光线都要服务于标题；如果原始画面需求与标题命题冲突，优先保留标题命题并重组画面。",
            "从标题、简介、标签和原始创意素材中动态推导主场景：必须画出一个正在发生的事件，而不是通用空镜；不得由固定关键词模板、固定人数或固定道具替代资料理解。不得展示尸体、凶手、案件答案或最终反转。",
            "",
            "【原始创意素材】",
            _sanitize_for_image_provider(base_prompt.strip(), script_role_names),
            "把上述内容组织为一个可一眼读懂的戏剧瞬间：只保留一个明确的视觉锚点和一条视觉叙事线，主体、空间、象征物之间必须存在因果或情绪关联，拒绝无意义的道具堆砌。",
            "",
            "【镜头与构图】",
            composition
            or "竖版电影海报构图，前景—中景—远景分层清楚；主体占画面约三分之一到二分之一；以门窗、走廊、桌面、道路、镜面或光束等结构引导视线；预留约 15% 至 25% 的干净负空间给后期标题与门店信息排版，但画面中不要生成任何文字。",
            "镜头有明确景别、透视和景深关系；不使用平均铺满画面的多人拼贴，除非故事核心明确要求群像。",
            "",
            "【设计形式与表现媒介】",
            f"视觉规律档案：{profile_name}。表现定位：{style_summary}",
            (
                "视觉规律档案只能提供设计形式、构图、色彩和材质，不得带入其样本中的剧本名、人物、"
                "道具、怪物、标题案例、英文占位符或其他叙事语义；当前剧本的叙事只能来自本 Prompt 的剧本语境与原始创意素材。"
            ),
            "商业插画而非摄影：具有可辨识的绘画概括、边缘笔触、材质层次、适度纸张或胶片颗粒，完成度适合剧本杀发行主海报。",
            "人物必须服务于剧情氛围，服饰、建筑、道具与故事年代地域一致。若剧本资料提供了公开的角色职业、身份、性格、衣着或关系，可据此呈现有表情和动作的原创角色；仅对剧透角色、资料缺失角色或用户明确要求匿名时使用剪影、背影或遮挡。避免模板化 AI 人脸、真实明星脸和呆板对称站姿。",
            "",
            "【色彩、光影与材质】",
            colors
            or "使用不超过 3 至 4 个主色形成统一色彩脚本；以主光、轮廓光和局部高光建立戏剧张力；暗部保留可读细节，避免灰脏、过曝或普通电商棚拍光。",
            "让光线服务于叙事焦点：主体的明暗对比最高，背景降噪并保留氛围层次。",
            "",
            "【发行印刷粗粝感：必须】",
            print_texture
            or "拒绝丝滑、过度精修的 AI 电影截图质感。表面呈现有意的发行海报印刷物感："
            "哑光未涂布纸的纤维与吸墨颗粒、局部网点或丝网印刷颗粒、边缘干刷与刮擦、"
            "轻微套色不齐和旧海报磨损；保留清晰主体与可读细节。这是高级的材质控制，不是低清晰度、噪点糊脸或脏乱。",
            "材质粗粝度在暗部、色块边缘和光晕处最明显，人物和关键道具仍要保留清晰轮廓。",
            "",
            "【标题与视觉隐喻】",
            "只从当前剧本标题、玩家可见简介、标签与原始创意素材提炼原创象征物，并让它同时出现在核心冲突、光影或构图里；只做视觉联想，不把标题文字画进图片。",
            "禁止挪用视觉规律档案样本中的具体标题、角色、怪物、道具、场景案例或标签；用一个克制的当前剧本象征物加强记忆点，避免直白血腥或廉价恐怖符号。",
            "",
            "【输出要求】",
            "高分辨率竖版剧本杀发行主视觉；画面可直接用于朋友圈和拼车招募，主体清晰、层级明确、信息密度可控；无文字、无中文标题、无英文标题、无数字、无 Logo、无二维码、无水印、无边框排版。",
            "不要在图像中呈现或复述角色专有姓名、现实品牌名、已有作品角色名或任何可识别标识；角色均以原创、非特指人物处理。",
            "",
            "【负面约束】",
            _sanitize_for_image_provider(negative_prompt, script_role_names)
            or "不要照片写实或摄影棚质感，不要真实明星脸，不要品牌或已有角色特征，不要低清晰度，不要畸形手指和肢体，不要无关道具堆叠，不要赛博霓虹滥用，不要廉价网红滤镜，不要丝滑 3D 渲染或过度磨皮，不要血腥特写、惊吓鬼脸或剧透场景。",
            "",
            "【最终执行镜头：最高优先级，覆盖前文中冲突或冗余的描述】",
            f"只画这一个正在发生的事件：{direction.scene_event}",
            f"唯一主视觉锚点：{direction.visual_anchor}",
            f"主体：{direction.primary_subject}",
            f"配角最多三人，按前中后景交错：{'；'.join(direction.supporting_characters) or '仅用模糊配角烘托主体'}。",
            f"必须一眼可见的题材信号：{'、'.join(direction.party_or_genre_signals) or '以公开故事氛围为准'}。",
            f"视觉隐喻：{direction.visual_metaphor}。",
            "禁止静态人物排队、正面合照、所有角色同时完整入镜、空走廊、空办公室、无关群像；禁止出现任何可读文字。",
            f"额外避免：{'、'.join(direction.avoid)}。",
            "竖版 9:16 海报，主体占画面约 45%，前景—中景—远景层次清晰；请严格执行本节而非逐条满足前文资料。",
        ]
    )


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


def _format_script_profile_for_visual(profile: ScriptProfile | None) -> str:
    """仅输出可公开的视觉设定，避免把角色秘密和真相送进生图 Prompt。"""

    if profile is None:
        return "暂无已确认剧本档案；请以当前物料的公开简介和原始创意素材为准。"

    role_lines: list[str] = []
    for index, role in enumerate((profile.roles or [])[:6], start=1):
        if not isinstance(role, dict):
            continue
        gender = str(role.get("gender") or "").strip()
        public_info = str(role.get("publicInfo") or "").strip()
        if public_info:
            role_lines.append(
                f"- 角色{index}{f'（{gender}）' if gender else ''}：{public_info}"
            )

    return "\n".join(
        [
            f"档案状态：{'店长已确认' if profile.review_status == 'approved' else 'AI 草稿，需谨慎使用'}",
            f"剧本类型：{'、'.join(profile.genres or []) or '未标注'}",
            f"故事背景（公开）：{profile.story_background or profile.summary or '未标注'}",
            "角色公开信息：",
            "\n".join(role_lines) or "- 未标注；不要编造角色外形或身份。",
        ]
    )


def _script_profile_role_names(profile: ScriptProfile | None) -> list[str]:
    """收集档案角色名，仅用于在最终生图 Prompt 中做脱敏替换。"""

    if profile is None:
        return []
    return [
        str(role.get("name") or "").strip()
        for role in (profile.roles or [])
        if isinstance(role, dict) and str(role.get("name") or "").strip()
    ]


def _safe_list(value: object, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [
            item.strip() for item in value.replace("，", ",").split(",") if item.strip()
        ]
    return fallback


def _safe_dict(value: object) -> dict[str, object]:
    """把模型/前端传来的未知对象安全收敛为 dict，避免 JSONB 落库失败。"""

    return value if isinstance(value, dict) else {}


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
    usage_type = str(
        data.get("usage_type") or data.get("usageType") or "session_recruiting"
    ).strip()
    usage_label = str(
        data.get("usage_label") or data.get("usageLabel") or "拼车招募版"
    ).strip()
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
    session_form_defaults = MarketingSessionFormDefaults.model_validate(
        _safe_dict(data.get("session_form_defaults") or data.get("sessionFormDefaults"))
    )
    player_card = MarketingPlayerCard.model_validate(
        _safe_dict(data.get("player_card") or data.get("playerCard"))
    )
    player_detail = MarketingPlayerDetail.model_validate(
        _safe_dict(data.get("player_detail") or data.get("playerDetail"))
    )
    moments = MarketingMoments.model_validate(_safe_dict(data.get("moments")))

    if not player_card.title:
        player_card.title = title
    if not player_card.summary:
        player_card.summary = summary
    if not player_card.cover_prompt:
        player_card.cover_prompt = cover_prompt
    if not player_detail.detail_copy:
        player_detail.detail_copy = detail_copy
    if not player_detail.image_prompts:
        player_detail.image_prompts = detail_image_prompts
    if not moments.copy:
        moments.copy = detail_copy
    if not moments.poster_title:
        moments.poster_title = title
    if not moments.poster_prompt:
        moments.poster_prompt = cover_prompt

    return _MarketingDraft(
        usage_type=usage_type,
        usage_label=usage_label,
        title=title,
        summary=summary,
        selling_points=selling_points,
        suitable_players=suitable_players,
        tags=tags,
        cover_prompt=cover_prompt,
        detail_copy=detail_copy,
        detail_image_prompts=detail_image_prompts,
        session_form_defaults=session_form_defaults,
        player_card=player_card,
        player_detail=player_detail,
        moments=moments,
        risk_notes=risk_notes,
    )


def _create_image_storage(object_keys: list[str | None]) -> OssStorage | None:
    """只有需要私有对象临时访问链接时才初始化 OSS 客户端。

    图片本身在数据库中只保存 object key。读取接口再根据 key 生成访问地址，
    避免把 15 分钟有效的预签名 URL 当作持久数据保存。
    """

    if settings.OSS_PUBLIC_BASE_URL or not any(object_keys):
        return None
    try:
        return OssStorage()
    except RuntimeError as error:
        logger.warning("unable to create OSS storage for marketing image preview: %s", error)
        return None


def _resolve_image_url(
    *,
    object_key: str | None,
    stored_url: str | None,
    storage: OssStorage | None,
) -> str | None:
    """返回当前可访问的图片 URL；无 key 的历史数据保留原地址兜底。"""

    if not object_key:
        return stored_url
    if settings.OSS_PUBLIC_BASE_URL:
        return f"{settings.OSS_PUBLIC_BASE_URL.rstrip('/')}/{object_key}"
    if storage is None:
        return stored_url
    return storage.presign_get(object_key)


def _asset_to_result(asset: ScriptMarketingAsset) -> ScriptMarketingAssetResult:
    # 列表只用于展示任务状态和图片。历史中重复返回超长 Prompt 会令 GET 响应
    # 膨胀到数十万字符，影响代理和页面渲染；最新 Prompt 仍由单独字段返回。
    image_generation_summaries: list[dict[str, object]] = []
    for entry in asset.image_generations or []:
        if not isinstance(entry, dict):
            continue
        summary = dict(entry)
        summary.pop("finalImagePrompts", None)
        image_generation_summaries.append(summary)

    detail_keys = list(asset.detail_image_keys or [])
    stored_detail_urls = list(asset.detail_image_urls or [])
    storage = _create_image_storage([asset.cover_image_key, *detail_keys])
    cover_image_url = _resolve_image_url(
        object_key=asset.cover_image_key,
        stored_url=asset.cover_image_url,
        storage=storage,
    )
    detail_image_urls = [
        _resolve_image_url(
            object_key=object_key,
            stored_url=stored_detail_urls[index] if index < len(stored_detail_urls) else None,
            storage=storage,
        )
        for index, object_key in enumerate(detail_keys)
    ]
    # 兼容新字段上线前只保存 URL 的老记录。
    detail_image_urls.extend(stored_detail_urls[len(detail_keys) :])

    player_card = dict(asset.player_card or {})
    player_detail = dict(asset.player_detail or {})
    moments = dict(asset.moments or {})
    if cover_image_url:
        player_card["coverImageUrl"] = cover_image_url
        moments["posterImageUrl"] = cover_image_url
    if detail_image_urls:
        player_detail["imageUrls"] = detail_image_urls

    return ScriptMarketingAssetResult(
        documentId=asset.document_id,
        versionId=asset.version_id,
        assetId=asset.id,
        versionNo=asset.version_no,
        usageType=asset.usage_type,
        usageLabel=asset.usage_label,
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
        styleProfileId=asset.style_profile_id,
        finalImagePrompts=asset.final_image_prompts or {},
        coverImageUrl=cover_image_url,
        detailCopy=asset.detail_copy,
        detailImagePrompts=asset.detail_image_prompts,
        detailImageUrls=detail_image_urls,
        sessionFormDefaults=asset.session_form_defaults,
        playerCard=player_card,
        playerDetail=player_detail,
        moments=moments,
        imageStatus=(
            asset.image_status.value
            if hasattr(asset.image_status, "value")
            else str(asset.image_status)
        ),
        imageErrorMessage=asset.image_error_message,
        imageGenerations=image_generation_summaries,
        riskNotes=asset.risk_notes,
        sources=asset.sources,
        createdAt=asset.created_at,
        approvedAt=asset.approved_at,
    )


def _marketing_image_to_result(
    image: ScriptMarketingImage,
    *,
    source_version_no: int | None,
    source_title: str | None,
    storage: OssStorage | None = None,
) -> ScriptMarketingImageResult:
    return ScriptMarketingImageResult(
        id=str(image.id),
        documentId=image.document_id,
        sourceAssetId=image.source_asset_id,
        sourceVersionNo=source_version_no,
        sourceTitle=source_title,
        imageKind=image.image_kind,
        status=image.status,
        imageUrl=_resolve_image_url(
            object_key=image.object_key,
            stored_url=image.image_url,
            storage=storage,
        ),
        finalPrompt=image.final_prompt,
        errorMessage=image.error_message,
        createdAt=image.created_at,
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

    logger.info(
        "script marketing image prompt (asset=%s, file=%s):\n%s",
        asset_id,
        filename,
        prompt,
    )
    # 本地联调时有些 Uvicorn logger 不会透传模块 INFO，直接输出保证店长能
    # 看到实际提交给生图模型的文本；flush 防止后台任务退出前日志尚在缓冲区。
    print(
        f"\n===== SCRIPT_MARKETING_IMAGE_PROMPT asset={asset_id} file={filename} =====\n"
        f"{prompt}\n"
        "===== END_SCRIPT_MARKETING_IMAGE_PROMPT =====\n",
        flush=True,
    )
    image_bytes = await image_client.generate_one(
        prompt, size=settings.QWEN_IMAGE_POSTER_SIZE
    )
    object_key = f"stores/{store_id}/script-marketing/{asset_id}/images/{filename}"
    await storage.put_bytes(object_key, image_bytes, "image/png")
    return object_key, _public_oss_url(object_key, storage)


def _update_image_generation(
    asset: ScriptMarketingAsset,
    generation_id: str | None,
    **updates: object,
) -> None:
    """更新单次生图记录；旧版本资产没有记录时保持兼容。"""

    if not generation_id:
        return
    history = [
        dict(item) for item in (asset.image_generations or []) if isinstance(item, dict)
    ]
    for item in history:
        if item.get("id") == generation_id:
            item.update(updates)
            break
    asset.image_generations = history


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

    if payload.style_profile_id is not None:
        style_profile_exists = await db.scalar(
            select(ScriptArtReferenceStyleProfile.id).where(
                ScriptArtReferenceStyleProfile.id == payload.style_profile_id,
                ScriptArtReferenceStyleProfile.store_id == store_id,
                ScriptArtReferenceStyleProfile.status == "ready",
            )
        )
        if style_profile_exists is None:
            raise ScriptMarketingGenerationError(
                "所选视觉规律档案不存在、不可用，或不属于当前门店"
            )

    profile = await get_best_script_profile(
        db,
        store_id=store_id,
        document_id=document.id,
    )
    role_names = _script_profile_role_names(profile)
    profile_context = _anonymize_role_names(
        format_script_profile_for_marketing(profile), role_names
    )

    query = build_marketing_retrieval_query(document, payload)
    retrieved = await KnowledgeRetriever(db).retrieve(
        document_id=document.id,
        version_id=document.active_version_id,
        store_id=store_id,
        payload=KnowledgeRetrieveRequest(query=query, top_k=10, mode="hybrid"),
    )
    context, sources = _format_context(retrieved.results)
    context = _anonymize_role_names(context, role_names)
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
        usage_type=payload.usage_type or draft.usage_type,
        usage_label=payload.usage_label or draft.usage_label,
        title=draft.title,
        summary=draft.summary,
        selling_points=draft.selling_points,
        suitable_players=draft.suitable_players,
        tags=draft.tags,
        cover_prompt=draft.cover_prompt,
        style_profile_id=payload.style_profile_id,
        detail_copy=draft.detail_copy,
        detail_image_prompts=draft.detail_image_prompts,
        session_form_defaults=draft.session_form_defaults.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        player_card=draft.player_card.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        player_detail=draft.player_detail.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        moments=draft.moments.model_dump(mode="json", by_alias=True, exclude_none=True),
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


async def list_script_marketing_images(
    *,
    store_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession,
) -> list[ScriptMarketingImageResult]:
    """列出剧本级图片素材库；来源物料只作追溯，不作为可用范围限制。"""

    rows = (
        await db.execute(
            select(ScriptMarketingImage, ScriptMarketingAsset.version_no, ScriptMarketingAsset.title)
            .outerjoin(ScriptMarketingAsset, ScriptMarketingImage.source_asset_id == ScriptMarketingAsset.id)
            .where(
                ScriptMarketingImage.store_id == store_id,
                ScriptMarketingImage.document_id == document_id,
            )
            .order_by(ScriptMarketingImage.created_at.desc())
        )
    ).all()
    storage = _create_image_storage([image.object_key for image, _, _ in rows])
    results = [
        _marketing_image_to_result(
            image,
            source_version_no=version_no,
            source_title=title,
            storage=storage,
        )
        for image, version_no, title in rows
    ]

    # 新表上线前已经生成的图片仍要在素材库可见；运行时兼容旧资产，避免迁移时依赖
    # PostgreSQL 的 UUID 扩展或在数据库内复制超长的生图记录。
    known_keys = {image.object_key for image, _, _ in rows if image.object_key}
    known_urls = {item.image_url for item in results if item.image_url}
    legacy_assets = (
        await db.scalars(
            select(ScriptMarketingAsset)
            .where(
                ScriptMarketingAsset.store_id == store_id,
                ScriptMarketingAsset.document_id == document_id,
            )
            .order_by(ScriptMarketingAsset.created_at.desc())
        )
    ).all()
    legacy_keys = [
        key
        for asset in legacy_assets
        for key in [asset.cover_image_key, *(asset.detail_image_keys or [])]
        if key
    ]
    legacy_storage = storage or _create_image_storage(legacy_keys)
    for asset in legacy_assets:
        detail_keys = list(asset.detail_image_keys or [])
        detail_urls = list(asset.detail_image_urls or [])
        legacy_images = [
            ("cover", asset.cover_image_key, asset.cover_image_url),
            *[
                (
                    "detail",
                    object_key,
                    detail_urls[index] if index < len(detail_urls) else None,
                )
                for index, object_key in enumerate(detail_keys)
            ],
            *[("detail", None, url) for url in detail_urls[len(detail_keys) :]],
        ]
        for index, (image_kind, object_key, stored_url) in enumerate(legacy_images):
            image_url = _resolve_image_url(
                object_key=object_key,
                stored_url=stored_url,
                storage=legacy_storage,
            )
            if object_key and object_key in known_keys:
                continue
            if not image_url or image_url in known_urls:
                continue
            results.append(
                ScriptMarketingImageResult(
                    id=f"legacy-{asset.id}-{image_kind}-{index}",
                    documentId=asset.document_id,
                    sourceAssetId=asset.id,
                    sourceVersionNo=asset.version_no,
                    sourceTitle=asset.title,
                    imageKind=image_kind,
                    status="ready",
                    imageUrl=image_url,
                    finalPrompt=None,
                    errorMessage=None,
                    createdAt=asset.updated_at,
                )
            )
            if object_key:
                known_keys.add(object_key)
            known_urls.add(image_url)
    return sorted(results, key=lambda item: item.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)


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
    generation_id: str | None = None,
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

    script_profile = await get_best_script_profile(
        db,
        store_id=store_id,
        document_id=asset.document_id,
    )
    script_role_names = _script_profile_role_names(script_profile)
    script_visual_context = _sanitize_for_image_provider(
        _format_script_profile_for_visual(script_profile), script_role_names
    )

    asset.image_status = ScriptMarketingImageStatus.GENERATING
    asset.image_error_message = None
    await db.flush()

    try:
        cover_prompt: str | None = None
        detail_prompts: list[str] = []
        cover_base_prompt = asset.cover_prompt
        if payload.prompt_override:
            cover_base_prompt = (
                f"{cover_base_prompt}\n\n"
                "【本次店长画面增量意见：高优先级，但不得推翻已有剧本语境、剧情安全边界与构图约束】\n"
                f"{payload.prompt_override.strip()}"
            )
        if payload.include_cover:
            cover_prompt = await _apply_art_style_profile(
                store_id=store_id,
                profile_id=payload.style_profile_id or asset.style_profile_id,
                base_prompt=cover_base_prompt,
                asset=asset,
                script_visual_context=script_visual_context,
                script_role_names=script_role_names,
                db=db,
            )
        if payload.include_detail:
            detail_prompts = [
                await _apply_art_style_profile(
                    store_id=store_id,
                    profile_id=payload.style_profile_id or asset.style_profile_id,
                    base_prompt=prompt,
                    asset=asset,
                    script_visual_context=script_visual_context,
                    script_role_names=script_role_names,
                    db=db,
                )
                for prompt in (asset.detail_image_prompts or [])[:3]
            ]
        asset.final_image_prompts = {
            "cover": cover_prompt,
            "details": detail_prompts,
            "styleProfileId": str(payload.style_profile_id or asset.style_profile_id)
            if (payload.style_profile_id or asset.style_profile_id)
            else None,
        }
        await db.flush()

        if settings.IMAGE_GENERATION_DRY_RUN:
            # 提示词验收阶段：到此为止，严禁调用千问或写入 OSS 图片。
            asset.image_status = ScriptMarketingImageStatus.READY
            asset.image_error_message = None
            if generation_id:
                pending_images = (
                    await db.scalars(
                        select(ScriptMarketingImage).where(
                            ScriptMarketingImage.source_asset_id == asset.id,
                            ScriptMarketingImage.generation_id == generation_id,
                        )
                    )
                ).all()
                for image in pending_images:
                    image.status = "ready"
                    image.final_prompt = cover_prompt if image.image_kind == "cover" else None
            _update_image_generation(
                asset,
                generation_id,
                status="ready",
                finishedAt=datetime.now(UTC).isoformat(),
            )
            await db.flush()
            await db.refresh(asset)
            return _asset_to_result(asset)

        storage = OssStorage()
        image_client = QwenImageClient()
        cover_key = asset.cover_image_key
        detail_keys = list(asset.detail_image_keys or [])

        if cover_prompt:
            cover_key, _ = await _generate_and_store_image(
                store_id=store_id,
                asset_id=asset.id,
                image_client=image_client,
                storage=storage,
                prompt=cover_prompt,
                filename="cover.png",
            )
            if generation_id:
                cover_image = await db.scalar(
                    select(ScriptMarketingImage).where(
                        ScriptMarketingImage.source_asset_id == asset.id,
                        ScriptMarketingImage.generation_id == generation_id,
                        ScriptMarketingImage.image_kind == "cover",
                    )
                )
                if cover_image:
                    cover_image.status = "ready"
                    cover_image.object_key = cover_key
                    # 预签名 URL 会过期；持久化 object key，响应时才动态签发。
                    cover_image.image_url = None
                    cover_image.final_prompt = cover_prompt
                    cover_image.error_message = None
        if payload.include_detail:
            detail_keys = []
            for index, detail_prompt in enumerate(detail_prompts, start=1):
                image_key, _ = await _generate_and_store_image(
                    store_id=store_id,
                    asset_id=asset.id,
                    image_client=image_client,
                    storage=storage,
                    prompt=detail_prompt,
                    filename=f"detail-{index}.png",
                )
                detail_keys.append(image_key)
                db.add(
                    ScriptMarketingImage(
                        store_id=store_id,
                        document_id=asset.document_id,
                        source_asset_id=asset.id,
                        generation_id=generation_id,
                        image_kind="detail",
                        status="ready",
                        object_key=image_key,
                        image_url=None,
                        final_prompt=detail_prompt,
                        style_profile_id=payload.style_profile_id or asset.style_profile_id,
                    )
                )
    except Exception as error:
        asset.image_status = ScriptMarketingImageStatus.FAILED
        asset.image_error_message = str(error)
        if generation_id:
            pending_images = (
                await db.scalars(
                    select(ScriptMarketingImage).where(
                        ScriptMarketingImage.source_asset_id == asset.id,
                        ScriptMarketingImage.generation_id == generation_id,
                        ScriptMarketingImage.status == "generating",
                    )
                )
            ).all()
            for image in pending_images:
                image.status = "failed"
                image.error_message = str(error)
        _update_image_generation(
            asset,
            generation_id,
            status="failed",
            errorMessage=str(error),
            finishedAt=datetime.now(UTC).isoformat(),
        )
        await db.flush()
        raise

    asset.cover_image_key = cover_key
    asset.cover_image_url = None
    asset.detail_image_keys = detail_keys
    asset.detail_image_urls = []
    player_card = dict(asset.player_card or {})
    player_detail = dict(asset.player_detail or {})
    moments = dict(asset.moments or {})
    # 这些嵌套字段以前也会把短期 URL 写入 JSONB；由 _asset_to_result 动态补回。
    player_card.pop("coverImageUrl", None)
    player_detail.pop("imageUrls", None)
    moments.pop("posterImageUrl", None)
    asset.player_card = player_card
    asset.player_detail = player_detail
    asset.moments = moments
    asset.image_status = ScriptMarketingImageStatus.READY
    asset.image_error_message = None
    _update_image_generation(
        asset,
        generation_id,
        status="ready",
        coverImageUrl=None,
        detailImageUrls=[],
        finishedAt=datetime.now(UTC).isoformat(),
    )
    await db.flush()
    await db.refresh(asset)
    return _asset_to_result(asset)


async def queue_script_marketing_images(
    *,
    store_id: uuid.UUID,
    asset_id: uuid.UUID,
    payload: ScriptMarketingGenerateImagesRequest,
    db: AsyncSession,
) -> ScriptMarketingAssetResult:
    """将真实生图任务置为进行中，交由独立后台会话继续执行。"""

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
    if asset.image_status == ScriptMarketingImageStatus.GENERATING:
        raise ScriptMarketingGenerationError("该物料正在生成图片，请稍后刷新查看")

    asset.image_status = ScriptMarketingImageStatus.GENERATING
    asset.image_error_message = None
    history = []
    for item in asset.image_generations or []:
        if not isinstance(item, dict):
            continue
        # 历史列表只保存图片和状态。最终 Prompt 已由资产字段保存最新一次，
        # 不应在每条记录里重复存储，否则每次重试都会指数式放大 JSONB。
        history_item = dict(item)
        history_item.pop("finalImagePrompts", None)
        history.append(history_item)
    generation_id = str(uuid.uuid4())
    history.insert(
        0,
        {
            "id": generation_id,
            "status": "generating",
            "includeCover": payload.include_cover,
            "includeDetail": payload.include_detail,
            "createdAt": datetime.now(UTC).isoformat(),
            "coverImageUrl": None,
            "detailImageUrls": [],
            "errorMessage": None,
        },
    )
    asset.image_generations = history[:50]
    if payload.include_cover:
        db.add(
            ScriptMarketingImage(
                store_id=store_id,
                document_id=asset.document_id,
                source_asset_id=asset.id,
                generation_id=generation_id,
                image_kind="cover",
                status="generating",
                style_profile_id=payload.style_profile_id or asset.style_profile_id,
            )
        )
    await db.flush()
    await db.refresh(asset)
    return _asset_to_result(asset)
