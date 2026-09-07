"""剧本档案 AI 抽取提示词。"""

SCRIPT_PROFILE_SYSTEM_PROMPT = (
    "你是剧本杀门店的资深内容运营和DM培训负责人。"
    "你的任务是从知识库RAG上下文中抽取一份结构化剧本档案，供门店创建场次、AI客服、运营物料和DM手册复用。"
    "只能基于上下文抽取，不确定的信息写 null 或空数组，不要编造凶手、角色关系、时长、人数。"
    "玩家可见字段必须避免剧透；真相摘要、剧透注意事项可以包含剧透，但必须谨慎。"
    "所有类型、标签、卖点、适合人群都使用中文。Return valid JSON."
)


SCRIPT_RELATIONSHIPS_SYSTEM_PROMPT = (
    "你是剧本杀门店的资深分角师和情感线分析师。"
    "你的任务是从角色资料和人物关系上下文中，抽取可用于玩家分角、DM带本和AI客服推荐的人物关系。"
    "不要只写简单关系名，要尽量抽取关系的情绪基调、发展弧线、玩家体验和DM注意事项。"
    "只能基于上下文，不确定不要编造。Return valid JSON."
)


def build_relationships_prompt(
    *,
    document_name: str,
    roles_context: str,
    relationships_context: str,
    story_background: str | None,
    truth_summary: str | None,
    role_names: list[str],
) -> str:
    return (
        f"剧本名称：{document_name}\n"
        f"已识别角色：{', '.join(role_names) or '暂无'}\n"
        f"故事背景摘要：{story_background or '暂无'}\n"
        f"真相摘要：{truth_summary or '暂无'}\n\n"
        f"角色信息上下文：\n{roles_context or '未检索到明确角色资料。'}\n\n"
        f"人物关系上下文：\n{relationships_context or '未检索到明确人物关系资料。'}\n\n"
        "请只输出 JSON 对象，字段包含：relationships, needsReviewReasons。\n"
        "relationships 最多 30 条，每条包含：\n"
        "- isOfficialPair: 是否官配/核心绑定关系。只有双向强绑定、影响角色动机或玩家体验的关系才写 true\n"
        "- importance: 0-100，这条关系在剧本体验中的重要度，不等于可信度\n"
        "- displayPriority: 展示优先级，1 最靠前。核心官配/主情感线优先，普通关系靠后\n"
        "- evidenceStrength: 0-100，资料证据强度。双方人物本都提到彼此则更高，单方提及则较低\n"
        "- from: 人物A\n"
        "- to: 人物B\n"
        "- relation: 关系大类，例如感情线、亲情线、友情线、师徒线、敌对、阵营、误解、守护、知己\n"
        "- subType: 关系细分，例如灵魂伴侣、青梅竹马、迷妹与角儿、隐忍守护、错过遗憾\n"
        "- emotionTone: 情绪基调数组，例如甜蜜、救赎、遗憾、克制、隐忍、守护、家国\n"
        "- relationshipArc: 关系发展弧线，80字以内\n"
        "- playerExperience: 玩家体验，60字以内，用于分角推荐\n"
        "- dmNotes: DM分角/控场提醒，80字以内\n"
        "- spoilerLevel: low/medium/high\n"
        "- confidence: 0-100\n"
        "- source: 来源文件或资料片段名\n\n"
        "重点抽取剧本杀玩家真正关心的关系线：\n"
        "\n官配/核心关系判断标准：\n"
        "1. 双方人物本都反复提及彼此，或关系直接影响角色动机、结局、选择。\n"
        "2. 存在明确爱情、婚约、恋人、灵魂伴侣、知音、救赎、错过、守护等描述。\n"
        "3. 玩家体验上足以作为分角卖点，例如超甜、虐恋、遗憾、双向奔赴、隐忍守护。\n"
        "4. 只是普通认识、普通同事、普通阵营关系，不要标记为 isOfficialPair=true。\n"
        "5. confidence 表示这条关系是否可信；importance 表示这条线是否重要；不要混用。\n"
        "6. displayPriority 用于前端展示排序：核心感情线/主关系优先，其次亲情友情，再其次普通阵营/背景关系。\n"
        "感情线、亲情线、友情线、家国线、师徒线、知己线、误解线、牺牲线、救赎线、遗憾线。\n"
        "如果只能判断浅层关系，也要在 needsReviewReasons 说明缺少哪些资料。\n"
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
        f"分区RAG上下文：\n{context}\n\n"
        "重要规则：\n"
        "1. 基础信息优先从【基础信息】分区抽取。\n"
        "2. 角色信息优先从【角色信息】分区抽取。\n"
        "3. DM流程、控场、开本风险优先从【DM流程】分区抽取。\n"
        "4. 机制规则优先从【机制规则】分区抽取。\n"
        "5. 真相、凶手、结局、反转只能从【真相结局】分区抽取。\n"
        "6. 物料、地图、道具、BGM、打印清单优先从【物料线索】分区抽取。\n"
        "7. 如果某个分区显示未检索到明确资料，不要编造对应字段。\n"
        "8. 所有缺失、不一致、低置信度内容，都写入 needs_review_reasons。\n\n"
        "9. 所有缺失、不一致、低置信度内容，都写入 needs_review_reasons。\n\n"
        "输出长度控制：\n"
        "1. roles 最多输出 12 个核心角色，每个角色 notes 控制在 80 字以内。\n"
        "2. summary/story_background/truth_summary 不要长篇复述原文，只做摘要。\n\n"
        "3. summary/story_background/truth_summary 不要长篇复述原文，只做摘要。\n\n"
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
        "- roles: 角色数组，每项可包含 name/gender/publicInfo/knownRelations/secretsOrRisks/notes，未知则少写\n"
        "- material_checklist: 开本物料清单数组\n"
        "- opening_risks: DM开本风险数组\n"
        "- spoiler_notes: 剧透注意事项数组\n"
        "- confidence_score: 0-100，综合评估资料完整度和抽取置信度\n"
        "- needs_review_reasons: 需要人工确认的原因数组\n"
    )
