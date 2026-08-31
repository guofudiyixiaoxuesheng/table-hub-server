"""解析剧本相关问题。"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from openai import LengthFinishReasonError, OpenAIError
from pydantic import ValidationError

from app.ai.scenes.script_rag.prompts import SCRIPT_QUESTION_PARSE_PROMPT
from app.ai.scenes.script_rag.schemas import ScriptQuestionAnalysis
from app.ai.scenes.script_rag.state import ScriptRagState
from app.integrations.llm.client import structured_chat_completion

logger = logging.getLogger(__name__)


def _rule_parse(message: str) -> ScriptQuestionAnalysis:
    question_type = "public_consulting"
    spoiler_risk = "low"
    if any(word in message for word in ("dm", "开本", "带本", "主持", "控场")):
        question_type = "dm_opening"
        spoiler_risk = "medium"
    if any(word in message for word in ("线索", "证据")):
        question_type = "clue_explanation"
        spoiler_risk = "medium"
    if any(word in message for word in ("机制", "规则", "玩法")):
        question_type = "mechanism_rule"
        spoiler_risk = "medium"
    if any(word in message for word in ("凶手", "真相", "复盘", "答案")):
        question_type = "truth_review"
        spoiler_risk = "high"
    if not message.strip():
        question_type = "missing_info"
    return ScriptQuestionAnalysis(
        question_type=question_type,  # type: ignore[arg-type]
        spoiler_risk=spoiler_risk,  # type: ignore[arg-type]
        confidence=0.55,
        reason="规则兜底解析",
    )


async def parse_script_question(state: ScriptRagState) -> ScriptRagState:
    message = state.get("message", "")
    try:
        result = await structured_chat_completion(
            ScriptQuestionAnalysis,
            [
                SystemMessage(content=SCRIPT_QUESTION_PARSE_PROMPT),
                HumanMessage(content=f"用户问题：{message}"),
            ],
            temperature=0,
            max_tokens=512,
        )
    except (LengthFinishReasonError, OpenAIError, ValidationError, ValueError) as exc:
        logger.warning("剧本问题解析失败，降级规则解析：%s", exc)
        result = _rule_parse(message.lower())

    return {
        **state,
        "question_type": result.question_type,
        "script_name": result.script_name,
        "act": result.act,
        "role_name": result.role_name,
        "spoiler_risk": result.spoiler_risk,
        "script_question_confidence": result.confidence,
        "script_question_reason": result.reason,
    }
