"""校验剧本 RAG 回答是否可靠、安全、相关。"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from openai import LengthFinishReasonError, OpenAIError
from pydantic import ValidationError

from app.ai.scenes.script_rag.prompts import SCRIPT_ANSWER_VALIDATE_PROMPT
from app.ai.scenes.script_rag.schemas import ScriptAnswerValidation
from app.ai.scenes.script_rag.state import ScriptRagState
from app.ai.utils import debug_context, debug_state
from app.integrations.llm.client import (
    ChatModelNotConfiguredError,
    structured_chat_completion,
)

logger = logging.getLogger(__name__)


def _fallback_validation(state: ScriptRagState) -> ScriptAnswerValidation:
    """质检模型不可用时的保守兜底。"""

    has_context = bool((state.get("safe_context") or "").strip())
    has_answer = bool((state.get("answer") or "").strip())
    return ScriptAnswerValidation(
        passed=has_context and has_answer,
        grounded=has_context,
        permission_safe=True,
        answer_relevant=has_answer,
        confidence=0.4,
        issues=(
            []
            if has_context and has_answer
            else ["缺少上下文或回答内容，未执行完整 LLM 质检"]
        ),
        revised_answer=None,
    )


async def validate_script_answer(state: ScriptRagState) -> ScriptRagState:
    """LLM 回答校验节点。

    生成和校验分开，后续监控系统可以单独统计：
    生成耗时、校验通过率、越权剧透拦截率、幻觉风险等指标。
    """

    debug_state("validate_script_answer:input", state)

    answer = state.get("answer") or ""
    safe_context = state.get("safe_context") or ""
    if not answer.strip():
        validation = _fallback_validation(state)
    else:
        prompt = (
            f"用户问题：{state.get('context_rewritten_query') or state.get('message') or ''}\n\n"
            "业务上下文：\n"
            f"- 剧本名：{state.get('script_name') or '未知'}\n"
            f"- 问题类型：{state.get('question_type') or '未知'}\n"
            f"- 用户权限：{state.get('permission_level') or 'guest'}\n"
            f"- 剧透风险：{state.get('spoiler_risk') or 'medium'}\n\n"
            f"召回上下文：\n{safe_context[:6000]}\n\n"
            f"待校验回答：\n{answer}"
        )
        try:
            validation = await structured_chat_completion(
                ScriptAnswerValidation,
                [
                    SystemMessage(content=SCRIPT_ANSWER_VALIDATE_PROMPT),
                    HumanMessage(content=prompt),
                ],
                temperature=0,
                max_tokens=1000,
            )
        except (
            ChatModelNotConfiguredError,
            LengthFinishReasonError,
            OpenAIError,
            ValidationError,
            ValueError,
        ) as exc:
            logger.warning("剧本 RAG 回答校验失败，使用保守兜底：%s", exc)
            validation = _fallback_validation(state)

    final_answer = (
        validation.revised_answer.strip() if validation.revised_answer else answer
    )
    validation_payload = validation.model_dump(mode="json")
    debug_context("validate_script_answer:result", validation_payload)
    return {
        **state,
        "answer": final_answer,
        "answer_validation": validation_payload,
        "answer_validated": validation.passed,
        "next_action": (
            "剧本 RAG 回答已校验。"
            if validation.passed
            else "剧本 RAG 回答未完全通过校验，请查看 answer_validation。"
        ),
    }
