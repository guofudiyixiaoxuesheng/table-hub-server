"""生成剧本 RAG 回答。"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from openai import LengthFinishReasonError, OpenAIError

from app.ai.scenes.script_rag.prompts import SCRIPT_RAG_ANSWER_PROMPT
from app.ai.scenes.script_rag.state import ScriptRagState
from app.ai.utils import debug_context, debug_state
from app.integrations.llm.client import (
    ChatModelNotConfiguredError,
    stream_chat_completion,
)

logger = logging.getLogger(__name__)


def _fallback_answer(state: ScriptRagState) -> str:
    query = state.get("context_rewritten_query") or state.get("rewritten_query") or state.get("message", "")
    chunks = state.get("retrieved_chunks", [])
    if chunks:
        return (
            "已完成剧本知识库召回。\n"
            f"检索问题：{query or '暂无'}\n"
            f"命中片段：{len(chunks)} 条\n"
            f"问题类型：{state.get('question_type', 'missing_info')}\n"
            f"权限级别：{state.get('permission_level', 'guest')}\n"
            f"剧透风险：{state.get('spoiler_risk', 'medium')}\n"
            "下一步可以把 safe_context 接入 LLM，生成正式的 DM 开本/RAG 回答。"
        )
    return (
        "没有召回到可用的剧本知识库片段。\n"
        f"检索问题：{query or '暂无'}\n"
        f"原因/下一步：{state.get('next_action') or '请确认剧本已完成加载、切片和向量化。'}"
    )


async def generate_script_answer(state: ScriptRagState) -> ScriptRagState:
    """基于 safe_context 生成剧本 RAG 回答。"""

    debug_state("generate_script_answer:input", state)

    query = state.get("context_rewritten_query") or state.get("rewritten_query") or state.get("message", "")
    safe_context = state.get("safe_context") or ""
    if not safe_context.strip():
        answer = _fallback_answer(state)
        return {
            **state,
            "answer": answer,
            "next_action": state.get("next_action", "没有可用上下文，无法生成 RAG 回答。"),
        }

    user_prompt = (
        f"用户问题：{query}\n\n"
        "业务上下文：\n"
        f"- 剧本名：{state.get('script_name') or '未知'}\n"
        f"- 幕次：{state.get('act') or '未知'}\n"
        f"- 角色：{state.get('role_name') or '无'}\n"
        f"- 问题类型：{state.get('question_type') or '未知'}\n"
        f"- 用户权限：{state.get('permission_level') or 'guest'}\n"
        f"- 剧透风险：{state.get('spoiler_risk') or 'medium'}\n\n"
        f"召回上下文：\n{safe_context}"
    )
    try:
        writer = get_stream_writer()
        parts: list[str] = []
        async for delta in stream_chat_completion(
            [
                SystemMessage(content=SCRIPT_RAG_ANSWER_PROMPT),
                HumanMessage(content=user_prompt),
            ],
            temperature=0.2,
            max_tokens=1800,
        ):
            parts.append(delta)
            writer({"type": "answer_delta", "delta": delta})
        answer = "".join(parts)
    except (
        ChatModelNotConfiguredError,
        LengthFinishReasonError,
        OpenAIError,
        ValueError,
    ) as exc:
        logger.warning("剧本 RAG 回答生成失败，降级为召回摘要：%s", exc)
        answer = _fallback_answer(state)

    debug_context(
        "generate_script_answer:result",
        {
            "query": query,
            "answer_length": len(answer),
            "retrieved_count": len(state.get("retrieved_chunks") or []),
        },
    )
    return {
        **state,
        "answer": answer,
        "next_action": "剧本 RAG 回答生成完成，进入回答校验。",
    }
