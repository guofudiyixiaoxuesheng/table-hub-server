"""主持人开本手册生成提示词。

第一版用固定章节模板，后续可以根据剧本类型动态增减章节。
"""

from __future__ import annotations

import json
from collections.abc import Mapping

MANUAL_SYSTEM_PROMPT = (
    "你是剧本杀门店的资深 DM 培训负责人，擅长把剧本资料整理成专业、可执行的主持人开本手册。"
    "必须严格基于给定 RAG 上下文，不要编造规则、人物关系或结局。"
    "这是门店内部 DM 文档，可以包含主持流程、机制、控场和剧透风险提示；"
    "但所有危险动作都必须给出安全提醒，所有不确定信息都要标注“需人工确认”。"
    "输出 Markdown，结构清晰，适合新 DM 开本时边看边执行。"
)

SECTION_SPECS: list[dict[str, object]] = [
    {
        "key": "guide",
        "title": "手册导览",
        "goal": "说明本手册如何使用，给出章节导览和首次开本建议。",
        "query": "DM 开本手册 导览 使用建议 章节结构 首次开本重点",
    },
    {
        "key": "prep_checklist",
        "title": "第一部分：开本前准备清单",
        "goal": "整理物料、设备、BGM、表格、场景布置和开场前自检清单。",
        "query": "开本前准备 物料 道具 BGM 表格 场景布置 DM自检",
    },
    {
        "key": "role_performance",
        "title": "第二部分：角色与演绎指南",
        "goal": "整理 NPC / DM 角色人设、关键台词、动作、语气和切换技巧。",
        "query": "NPC 人设 关键台词 动作 演绎 DM切换技巧",
    },
    {
        "key": "act_flow",
        "title": "第三部分：分幕流程手册",
        "goal": "按开场、每一幕、结局整理目标、时长、流程、BGM、话术、DM 操作和转场。",
        "query": "分幕流程 开场 第一幕 第二幕 第三幕 第四幕 结局 BGM 话术 转场",
    },
    {
        "key": "rules_faq",
        "title": "第四部分：机制与规则详解",
        "goal": "整理核心机制、计分规则、争议判例和主持人口径。",
        "query": "机制规则 计分 好运值 告发 道具 偷窃 数字炸弹 争议判例",
    },
    {
        "key": "emergency_plan",
        "title": "第五部分：应急预案",
        "goal": "整理玩家摆烂、争议、超时、情绪低落、道具丢失、剧透等应急处理。",
        "query": "应急预案 玩家摆烂 规则争议 超时 情绪低落 道具丢失 剧透",
    },
    {
        "key": "appendix",
        "title": "附录：开本记录表",
        "goal": "生成开本信息、玩家反馈、主持人自评和备注记录模板。",
        "query": "开本记录表 玩家反馈 主持人自评 复盘 备注 模板",
    },
]

MANUAL_VALIDATION_SYSTEM_PROMPT = (
    "你是剧本杀门店的资深 DM 教研负责人，负责审核 AI 生成的主持人开本手册。"
    "你要严格检查手册是否适合真实门店开本使用，尤其关注完整性、可执行性、剧透风险、规则准确性和新手友好度。"
    "请只输出 JSON，不要输出 Markdown，不要输出额外解释。"
)


def build_manual_validation_prompt(
    *,
    script_name: str,
    manual_markdown: str,
    target_dm_level: str,
    sources: list[str],
) -> str:
    return (
        f"剧本名称：{script_name}\n"
        f"目标 DM 水平：{target_dm_level}\n"
        f"引用来源：{', '.join(sources) if sources else '无'}\n\n"
        f"待审核主持人手册：\n{manual_markdown}\n\n"
        "请从以下维度审核，并只输出 JSON：\n"
        "{\n"
        '  "passed": true,\n'
        '  "score": 0.85,\n'
        '  "completeness": 0.8,\n'
        '  "actionability": 0.9,\n'
        '  "faithfulness": 0.85,\n'
        '  "spoilerSafety": 0.8,\n'
        '  "missingSections": ["缺少第三幕详细控场流程"],\n'
        '  "riskNotes": ["部分规则可能需要人工确认"],\n'
        '  "suggestions": ["建议补充每幕预计时长和转场话术"],\n'
        '  "reason": "整体可用，但部分章节还需要补充。"\n'
        "}\n\n"
        "字段要求：\n"
        "1. passed：布尔值，score >= 0.75 且无严重风险时为 true。\n"
        "2. score：总体分数，0 到 1。\n"
        "3. completeness：完整度，是否覆盖准备、角色、流程、规则、应急、附录。\n"
        "4. actionability：可执行性，是否有清单、步骤、话术、注意事项。\n"
        "5. faithfulness：忠实度，是否严格基于资料，是否存在编造。\n"
        "6. spoilerSafety：剧透安全，是否清楚提醒 DM / 玩家信息隔离。\n"
        "7. missingSections：缺失内容列表，没有则返回空数组。\n"
        "8. riskNotes：风险点列表，没有则返回空数组。\n"
        "9. suggestions：改进建议列表，没有则返回空数组。\n"
        "10. reason：一句话总结。\n"
    )


def build_section_prompt(
    *,
    script_name: str,
    section: Mapping[str, object],
    context: str,
    target_dm_level: str,
    extra_requirement: str | None,
    script_facts: dict[str, object] | None = None,
) -> str:
    """构造单个章节生成提示词。"""

    facts_text = json.dumps(script_facts or {}, ensure_ascii=False, indent=2)

    return (
        f"剧本名称：{script_name}\n"
        f"章节标题：{section['title']}\n"
        f"章节目标：{section['goal']}\n"
        f"目标 DM 水平：{target_dm_level}\n"
        f"额外要求：{extra_requirement or '无'}\n\n"
        f"RAG 上下文：\n{context}\n\n"
        f"全局事实锚点 JSON：\n{facts_text}\n\n"
        "请生成该章节 Markdown。要求：\n"
        "1. 内容要具体、可执行，尽量包含清单、步骤、话术或判例。\n"
        "2. 不要写本章以外的大量内容。\n"
        "3. 如果资料不足，保留章节但标注“需人工确认”。\n"
        "4. 不要虚构没有依据的卡牌数量、人物关系、结局条件。\n"
        "5. 如果章节内容与全局事实锚点冲突，必须以全局事实锚点为准；"
        "如果全局事实锚点标注“需人工确认”，不要擅自给出确定结论。\n"
    )


SCRIPT_FACTS_SYSTEM_PROMPT = (
    "你是剧本杀门店的资深 DM 教研负责人，负责从剧本资料中抽取全局事实锚点。"
    "这些事实将用于约束后续主持人手册生成，避免人物、凶手、机制、时间线前后矛盾。"
    "必须严格基于 RAG 上下文，不要编造。"
    "请只输出 JSON，不要输出 Markdown，不要输出额外解释。"
)


def build_script_facts_prompt(
    *,
    script_name: str,
    context: str,
) -> str:
    return (
        f"剧本名称：{script_name}\n\n"
        f"RAG 上下文：\n{context}\n\n"
        "请抽取剧本全局事实锚点，并只输出 JSON：\n"
        "{\n"
        '  "scriptName": "剧本名称",\n'
        '  "playerCount": "例如：7人；未知则写需人工确认",\n'
        '  "duration": "例如：4小时；未知则写需人工确认",\n'
        '  "genre": "例如：推理/机制/情感；未知则写需人工确认",\n'
        '  "coreMechanics": ["核心机制"],\n'
        '  "truthSummary": "真相摘要；无法确认则写需人工确认",\n'
        '  "killerOrCulprit": "凶手/关键责任人；无法确认则写需人工确认",\n'
        '  "keyRelationships": ["关键人物关系"],\n'
        '  "timeline": ["关键时间线"],\n'
        '  "endingConditions": ["结局/胜利/结算条件"],\n'
        '  "spoilerWarnings": ["需要特别隔离的剧透信息"],\n'
        '  "conflicts": ["资料内互相冲突的信息"],\n'
        '  "unknowns": ["资料不足、需要人工确认的信息"]\n'
        "}\n\n"
        "要求：\n"
        "1. 不确定就写“需人工确认”，不要猜。\n"
        "2. 如果不同资料对同一事实说法不同，必须写入 conflicts。\n"
        "3. 对新手 DM 开本有风险的信息，必须写入 spoilerWarnings。\n"
        "4. 只输出 JSON。"
    )
