"""父图业务分支占位处理器。

后续每个 handler 都可以逐步替换成独立子图：
- 拼车子图
- 剧本 RAG 子图
- 预约子图
- 客服 RAG 子图
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from openai import LengthFinishReasonError, OpenAIError

from app.ai.scenes.script_rag import build_script_rag_graph
from app.ai.state import AiMessage, ParentGraphState
from app.integrations.llm.client import ChatModelNotConfiguredError, chat_completion

logger = logging.getLogger(__name__)

script_rag_graph = build_script_rag_graph()


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


async def script_rag_handler(state: ParentGraphState) -> ParentGraphState:
    result = await script_rag_graph.ainvoke(state)
    scene_payload = {
        "questionType": result.get("question_type"),
        "scriptId": result.get("script_id"),
        "scriptName": result.get("script_name"),
        "act": result.get("act"),
        "roleName": result.get("role_name"),
        "permissionLevel": result.get("permission_level"),
        "spoilerRisk": result.get("spoiler_risk"),
        "filters": result.get("allowed_filters", {}),
        "retrievedCount": len(result.get("retrieved_chunks", [])),
    }
    return {
        **state,
        "answer": result.get("answer", state.get("answer", "")),
        "citations": result.get("citations", []),
        "next_action": result.get("next_action", ""),
        "scene_payload": scene_payload,
    }


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


def _recent_chat_messages(state: ParentGraphState, limit: int = 10) -> list[AiMessage]:
    return [
        item
        for item in state.get("messages", [])[-limit:]
        if item["role"] in {"user", "assistant", "system"}
    ]


def _casual_chat_fallback(state: ParentGraphState) -> ParentGraphState:
    query = state.get("rewritten_query") or state.get("message", "")
    answer = (
        f"收到，{query or '我在听'}。\n"
        "我可以先陪你聊聊；如果你后面想问拼车、剧本、预约或者门店规则，也可以直接说。"
    )
    return {**state, "answer": answer, "next_action": "引导用户进入拼车、剧本 RAG、预约或门店咨询。"}


async def casual_chat_handler(state: ParentGraphState) -> ParentGraphState:
    """业务相关度低时的自然闲聊，不急着导购。"""

    try:
        answer = await chat_completion(
            [
                SystemMessage(
                    content=(
                        "你是 TableHub 的轻量 AI 客服，也是一个自然、温和的聊天助手。"
                        "当前用户没有明确业务诉求时，先自然回应，不要急着推销、不要立刻列业务清单。"
                        "如果用户是在寒暄、自我介绍、表达情绪，就顺着回应，并结合上下文记住信息。"
                        "只有当用户主动提到拼车、剧本、预约、门店规则、DM 开本时，才轻轻引导到对应能力。"
                        "回复要短，1到3句话，中文口语化。"
                    )
                ),
                *_recent_chat_messages(state),
                HumanMessage(content=state.get("message", "")),
            ],
            temperature=0.6,
            max_tokens=300,
        )
        return {
            **state,
            "answer": answer,
            "next_action": "自然闲聊，必要时轻引导到业务能力。",
        }
    except (
        ChatModelNotConfiguredError,
        LengthFinishReasonError,
        OpenAIError,
        ValueError,
    ) as exc:
        logger.warning("闲聊模型调用失败，降级模板回复：%s", exc)
        return _casual_chat_fallback(state)


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
