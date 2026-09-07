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
        "视觉元素、禁止剧透的信息。"
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
        f"语气风格：{payload.tone}\n"
        f"是否避免剧透：{payload.avoid_spoilers}\n"
        f"额外要求：{payload.extra_requirement or '无'}\n\n"
        f"{profile_context}\n\n"
        f"【RAG 原始资料上下文】\n{rag_context}\n\n"
        "请只返回 JSON 对象，字段必须包含："
        "title, summary, selling_points, suitable_players, tags, cover_prompt, detail_copy, detail_image_prompts, session_form_defaults, risk_notes。\n"
        "其中 selling_points、suitable_players、tags 必须全部是中文。\n"
        "session_form_defaults 是给创建场次表单用的对象，建议包含："
        "title, description, durationMinutes, capacity, minPlayers, priceYuan, notes。"
        "如果资料无法确认时长、人数或价格，不要编造，字段可以省略或写 null。\n"
        "如果剧本档案与 RAG 原文冲突：已确认档案优先；未确认档案则在 risk_notes 中提醒店长复核。"
    )
