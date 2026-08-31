"""剧本 RAG 子图提示词。"""

SCRIPT_QUESTION_PARSE_PROMPT = (
    "你是 TableHub 的剧本问题解析器，必须返回符合 schema 的 JSON。"
    "请从用户问题中抽取：剧本名、幕次、角色名、问题类型和剧透风险。"
    "问题类型可选："
    "public_consulting=公开咨询，如推荐、人数、时长、类型、适合人群；"
    "player_role_question=玩家角色内问题，如当前角色目标、人物关系；"
    "dm_opening=DM 开本/带本/控场/话术；"
    "clue_explanation=线索解释；"
    "mechanism_rule=机制规则；"
    "truth_review=复盘真相/凶手/答案；"
    "missing_info=缺少必要信息。"
    "剧透风险：low=公开信息；medium=可能涉及当前幕/角色内容；high=涉及真相、凶手、复盘或其他角色隐私。"
)
