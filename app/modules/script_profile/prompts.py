"""剧本档案 AI 抽取提示词。"""

SCRIPT_PROFILE_SYSTEM_PROMPT = (
    "你是剧本杀门店的资深内容运营和DM培训负责人。"
    "你的任务是从知识库RAG上下文中抽取一份结构化剧本档案，供门店创建场次、AI客服、运营物料和DM手册复用。"
    "只能基于上下文抽取，不确定的信息写 null 或空数组，不要编造凶手、角色关系、时长、人数。"
    "玩家可见字段必须避免剧透；真相摘要、剧透注意事项可以包含剧透，但必须谨慎。"
    "所有类型、标签、卖点、适合人群都使用中文。Return valid JSON."
)


def build_script_profile_prompt(
    *,
    document_name: str,
    document_description: str | None,
    document_tags: list[str],
    document_genre: str | None,
    extra_requirement: str | None,
    context: str,
) -> str:
    return (
        f"知识库剧本名称：{document_name}\n"
        f"知识库说明：{document_description or '暂无'}\n"
        f"知识库类型：{document_genre or '未填写'}\n"
        f"已有标签：{', '.join(document_tags) or '暂无'}\n"
        f"店长补充要求：{extra_requirement or '无'}\n\n"
        f"RAG上下文：\n{context}\n\n"
        "请输出 JSON 对象，字段必须包含：\n"
        "- name: 剧本正式名称\n"
        "- alias_names: 剧本别名数组\n"
        "- genres: 中文类型数组，例如推理、硬核、还原、情感、机制、阵营、欢乐、恐怖、变格\n"
        "- player_count_min/player_count_max: 人数，没有依据就 null\n"
        "- duration_minutes: 时长分钟数，没有依据就 null\n"
        "- difficulty: 玩家难度中文描述\n"
        "- dm_difficulty: DM主持难度中文描述\n"
        "- summary: 玩家可见简介，严禁剧透\n"
        "- story_background: 故事背景摘要，尽量不剧透\n"
        "- truth_summary: 后台/DM可见真相摘要，没有明确资料就 null\n"
        "- selling_points: 玩家可见卖点数组\n"
        "- suitable_players: 适合玩家画像数组\n"
        "- core_mechanics: 核心机制数组\n"
        "- roles: 角色数组，每项可包含 name/gender/publicInfo/notes，未知则少写\n"
        "- material_checklist: 开本物料清单数组\n"
        "- opening_risks: DM开本风险数组\n"
        "- spoiler_notes: 剧透注意事项数组\n"
        "- confidence_score: 0-100，综合评估资料完整度和抽取置信度\n"
        "- needs_review_reasons: 需要人工确认的原因数组\n"
    )
