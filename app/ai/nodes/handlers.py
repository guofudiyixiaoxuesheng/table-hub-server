"""父图业务分支占位处理器。

后续每个 handler 都可以逐步替换成独立子图：
- 拼车子图
- 剧本 RAG 子图
- 预约子图
- 客服 RAG 子图
"""

from __future__ import annotations

from app.ai.state import ParentGraphState


def _build_answer(
    state: ParentGraphState,
    *,
    title: str,
    next_action: str,
) -> ParentGraphState:
    query = state.get("rewritten_query") or state.get("message", "")
    answer = (
        f"已进入【{title}】父图分支。\n"
        f"当前问题：{query or '暂无'}\n"
        f"识别意图：{state.get('intent', state.get('scene', 'fallback'))}"
        f"（置信度 {state.get('intent_confidence', 0):.2f}）\n"
        f"下一步：{next_action}"
    )
    return {**state, "answer": answer, "next_action": next_action}


def carpool_handler(state: ParentGraphState) -> ParentGraphState:
    return _build_answer(
        state,
        title="拼车助手",
        next_action="后续接拼车子图：按人数、时间、剧本偏好匹配可拼场次。",
    )


def script_rag_handler(state: ParentGraphState) -> ParentGraphState:
    return _build_answer(
        state,
        title="剧本 RAG 助手",
        next_action="后续接剧本 RAG 子图：解析剧本/角色/幕/问题类型，再按权限做检索、剧透控制和回答。",
    )


def reservation_handler(state: ParentGraphState) -> ParentGraphState:
    return _build_answer(
        state,
        title="预约咨询",
        next_action="后续接预约子图：场次查询、人数判断、预约码生成。",
    )


def store_faq_handler(state: ParentGraphState) -> ParentGraphState:
    return _build_answer(
        state,
        title="门店客服",
        next_action="后续接客服 RAG：知识库召回、精排、引用回答。",
    )


def fallback_handler(state: ParentGraphState) -> ParentGraphState:
    query = state.get("rewritten_query") or state.get("message", "")
    if state.get("intent") == "clarify_intent":
        answer = (
            "我有点不确定你具体想做哪类操作。\n"
            f"当前问题：{query or '暂无'}\n"
            f"原始判断：{state.get('raw_scene', 'unknown')}，"
            f"置信度 {state.get('intent_confidence', 0):.2f}\n"
            "你可以补充一下：是想拼车/拼场、问剧本相关问题、预约场次，还是咨询门店规则？"
        )
    else:
        answer = (
            "我还没识别出明确业务场景。\n"
            "你可以告诉我是想拼车、问剧本相关问题、预约场次，还是咨询门店规则？"
        )
    return {**state, "answer": answer, "next_action": "等待用户补充更明确的问题。"}
