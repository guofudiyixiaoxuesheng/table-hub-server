"""生成剧本 RAG 回答。"""

from __future__ import annotations

from app.ai.scenes.script_rag.state import ScriptRagState


def generate_script_answer(state: ScriptRagState) -> ScriptRagState:
    query = state.get("rewritten_query") or state.get("message", "")
    answer = (
        "已进入【剧本 RAG 子图】。\n"
        f"当前问题：{query or '暂无'}\n"
        f"问题类型：{state.get('question_type', 'missing_info')}\n"
        f"权限级别：{state.get('permission_level', 'guest')}\n"
        f"剧透风险：{state.get('spoiler_risk', 'medium')}\n"
        "下一步会接入 hybrid 检索：按剧本、幕、角色和权限过滤 chunk，再做剧透控制后回答。"
    )
    return {
        **state,
        "answer": answer,
        "next_action": "接入剧本 RAG 检索与剧透安全过滤。",
    }
