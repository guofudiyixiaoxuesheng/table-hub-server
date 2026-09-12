"""剧本 AI 运营物料生成提示词。

这里集中管理“运营物料”相关 prompt，service.py 只负责业务流程：
查剧本、查剧本档案、检索 RAG、调用模型、落库。
"""

from __future__ import annotations

from app.ai.scenes.script_marketing.schemas import ScriptMarketingGenerateRequest
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.script_profile.models import ScriptProfile

MARKETING_SYSTEM_PROMPT = (
    "你是剧本杀门店的 AI 运营助手，擅长把剧本资料转成玩家能看懂、店长能直接使用的宣传物料。"
    "必须优先遵守【剧本档案可信上下文】，再参考 RAG 上下文。"
    "不要编造关键剧情；默认不剧透凶手、隐藏身份、最终反转和 DM 手册答案。"
    "图片提示词要描述画面、风格、氛围、构图和禁忌，不要包含真实明星/IP侵权元素。"
    "主图提示词中，剧本标题的视觉命题优先级最高：先把标题转为一个可见的公开冲突、"
    "一个主视觉锚点和一个象征物，再补充场景与氛围；禁止只写泛泛的‘某时代办公室/某种颜色’。"
    "如可信资料包含角色公开身份、职业、关系、性格、衣着或外观线索，可将其转为角色的"
    "动作、表情、服装与站位；不得捏造资料中没有的角色设定，也不得泄露隐藏身份或真相。"
    "目标玩家默认是 18-30 岁年轻成年人：视觉应有当代青年商业海报和编辑设计感，角色默认是"
    "年轻成年人；若资料未明确年代、年龄或地域，不得擅自补成维多利亚古宅、老派绅士或老年角色。"
    "卖点、适合人群、标签必须使用中文短词，禁止输出 mystery_hardcore、mechanism 等英文枚举。"
    "Return valid JSON."
)


def purpose_label(purpose: str) -> str:
    return {
        "script_profile": "剧本资料页宣传",
        "session_fill": "创建/编辑场次自动填充",
        "cover_and_detail": "主图与详情图提示词",
    }.get(purpose, purpose)


def format_relationships(relationships: object) -> str:
    """把人物关系对象数组转成可读文本，避免 prompt 里出现 Python dict 噪音。"""

    if not isinstance(relationships, list):
        return "- 需人工确认"

    lines: list[str] = []
    for item in relationships[:12]:
        if isinstance(item, dict):
            from_name = item.get("from") or item.get("fromName") or "未知"
            to_name = item.get("to") or "未知"
            relation = item.get("relation") or "关系未标注"
            sub_type = item.get("subType") or ""
            arc = item.get("relationshipArc") or item.get("description") or ""
            is_core = "核心关系" if item.get("isOfficialPair") else "普通关系"
            lines.append(
                f"- {from_name} 与 {to_name}：{relation}{f' / {sub_type}' if sub_type else ''}（{is_core}）。{arc}"
            )
        elif str(item).strip():
            lines.append(f"- {item}")

    return "\n".join(lines) or "- 需人工确认"


def format_script_profile_for_marketing(profile: ScriptProfile | None) -> str:
    """把剧本档案整理成运营物料生成的高优先级上下文。"""

    if profile is None:
        return "暂无已生成剧本档案，请主要依据 RAG 上下文生成，并显式标注需人工确认的信息。"

    status_label = (
        "店长已确认" if profile.review_status == "approved" else "AI 生成未确认"
    )

    return f"""
【剧本档案可信上下文】
档案状态：{status_label}
剧本名称：{profile.name}
剧本类型：{", ".join(profile.genres or []) or "需人工确认"}
人数：{profile.player_count_min or "?"}-{profile.player_count_max or "?"} 人
时长：{profile.duration_minutes or "需人工确认"} 分钟
DM 难度：{profile.dm_difficulty or "需人工确认"}
一句话简介：{profile.summary or "需人工确认"}

玩家卖点：
{chr(10).join(f"- {item}" for item in (profile.selling_points or [])) or "- 需人工确认"}

适合玩家：
{chr(10).join(f"- {item}" for item in (profile.suitable_players or [])) or "- 需人工确认"}

核心机制：
{chr(10).join(f"- {item}" for item in (profile.core_mechanics or [])) or "- 需人工确认"}

人物关系：
{format_relationships(profile.relationships)}

开本风险：
{chr(10).join(f"- {item}" for item in (profile.opening_risks or [])) or "- 需人工确认"}

剧透提醒：
{chr(10).join(f"- {item}" for item in (profile.spoiler_notes or [])) or "- 需人工确认"}
""".strip()


def build_marketing_retrieval_query(
    document: KnowledgeDocument, payload: ScriptMarketingGenerateRequest
) -> str:
    return (
        f"为剧本《{document.name}》生成{purpose_label(payload.purpose)}需要的资料。"
        "重点提取：剧本类型、故事背景、玩家可见卖点、适合人群、氛围、时长人数线索、"
        "可公开的角色身份/职业/衣着/性格与关系线索、视觉元素、禁止剧透的信息。"
    )


def build_marketing_user_prompt(
    *,
    document: KnowledgeDocument,
    payload: ScriptMarketingGenerateRequest,
    profile_context: str,
    rag_context: str,
) -> str:
    return (
        f"剧本名称：{document.name}\n"
        f"剧本类型：{document.script_genre or '未分类'}\n"
        f"已有标签：{', '.join(document.tags or []) or '暂无'}\n"
        f"使用场景：{purpose_label(payload.purpose)}\n"
        f"物料版本：{payload.usage_label}（{payload.usage_type}）\n"
        f"语气风格：{payload.tone}\n"
        f"是否避免剧透：{payload.avoid_spoilers}\n"
        f"额外要求：{payload.extra_requirement or '无'}\n\n"
        f"{profile_context}\n\n"
        f"【RAG 原始资料上下文】\n{rag_context}\n\n"
        "请只返回 JSON 对象，字段必须包含：\n"
        "title, summary, selling_points, suitable_players, tags, cover_prompt, detail_copy, detail_image_prompts, "
        "session_form_defaults, player_card, player_detail, moments, risk_notes。\n"
        "其中 selling_points、suitable_players、tags 必须全部是中文。\n"
        "session_form_defaults 是给创建场次表单用的对象，字段建议包含："
        "title, description, durationMinutes, capacity, minPlayers, priceYuan, notes。\n"
        "player_card 是玩家端拼车列表卡片，字段建议包含：title, subtitle, summary, coverPrompt。\n"
        "player_detail 是玩家端详情页，字段建议包含：detailCopy, imagePrompts。\n"
        "moments 是朋友圈传播物料，字段建议包含：copy, posterTitle, posterSubtitle, posterPrompt。\n"
        "图片 prompt 必须是中文，强调画面氛围、构图、色彩、时代/题材元素，避免真实剧本封面复刻、避免照搬版权海报。\n"
        "其中 cover_prompt 的第一段必须是“标题视觉命题”：围绕剧本标题写出一个不剧透的公开冲突、"
        "一个主视觉锚点和一个象征物；标题语义优先级高于普通场景描述。"
        "cover_prompt 的第二段必须是“具体场景事件与角色表现”：根据标题、简介、可信档案和 RAG，"
        "描述画面中此刻发生的事件、角色之间的动作关系，以及有资料支撑时可见的身份、衣着和表情。"
        "不要用固定关键词案例或固定角色数量套模板；资料不足时使用非特指角色并避免编造。\n"
        "若资料没有明确年代或角色年龄，默认采用现代青年职场/社交语境和 20-35 岁成年角色；"
        "画面保持年轻、利落、具有当代编辑海报感，避免古董感、棕褐老电影感和明显年长的人物。\n"
        "如果资料无法确认时长、人数或价格，不要编造，字段可以省略或写 null。\n"
        "如果剧本档案与 RAG 原文冲突：已确认档案优先；未确认档案则在 risk_notes 中提醒店长复核。"
    )
