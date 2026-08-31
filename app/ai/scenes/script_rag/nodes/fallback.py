"""剧本 RAG 子图兜底节点。"""

from __future__ import annotations

from app.ai.scenes.script_rag.state import ScriptRagState


def missing_info_fallback(state: ScriptRagState) -> ScriptRagState:
    answer = (
        "我知道你在问剧本相关问题，但信息还不够。\n"
        "你可以补充：剧本名、角色名、当前第几幕，或者你是 DM 还是玩家。"
    )
    return {**state, "answer": answer, "next_action": "等待用户补充剧本/角色/幕次信息。"}


def spoiler_block(state: ScriptRagState) -> ScriptRagState:
    answer = (
        "这个问题可能涉及剧透或其他角色隐私。\n"
        "如果你是 DM 或店长，请先登录对应账号；如果你是玩家，可以补充你的角色和当前幕次，我会只给不剧透的提示。"
    )
    return {**state, "answer": answer, "next_action": "拦截高剧透风险问题。"}
