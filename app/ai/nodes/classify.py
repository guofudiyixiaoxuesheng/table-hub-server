"""父图入口分类节点。"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from openai import LengthFinishReasonError, OpenAIError
from pydantic import BaseModel, Field, field_validator

from app.ai.state import AiScene, ParentGraphState
from app.integrations.llm.client import structured_chat_completion

logger = logging.getLogger(__name__)

DM_KEYWORDS = ("dm", "主持", "开本", "带本", "复盘", "幕", "线索", "凶手", "剧透")
CARPOOL_KEYWORDS = (
    "拼车",
    "拼场",
    "拼局",
    "能拼",
    "可拼",
    "车队",
    "差几人",
    "组局",
    "上车",
    "缺人",
)
SCRIPT_RAG_KEYWORDS = (
    "剧本",
    "本子",
    "推荐",
    "类型",
    "几人本",
    "恐怖",
    "情感",
    "机制",
    "硬核",
    "角色",
    "任务",
    "线索",
    "凶手",
    "复盘",
    "真相",
    "开本",
    "带本",
)
RESERVATION_KEYWORDS = ("预约", "报名", "场次", "几点", "周末", "价格", "余位", "下单")
VALID_SCENES: set[str] = {
    "carpool",
    "script_rag",
    "reservation",
    "store_faq",
    "fallback",
}
INTENT_CONFIDENCE_THRESHOLD = 0.65


class IntentClassification(BaseModel):
    """模型意图识别结构化输出。"""

    scene: Literal[
        "carpool",
        "script_rag",
        "reservation",
        "store_faq",
        "fallback",
    ] = Field(description="用户消息所属业务场景")
    intent: str = Field(default="", description="用一句短语概括用户真实意图")
    confidence: float = Field(default=0.5, ge=0, le=1, description="识别置信度，范围 0 到 1")
    reason: str = Field(default="", description="一句话解释判断原因")

    @field_validator("intent", "reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        return value.strip() or "未提供"


def _normalize_scene(value: object) -> AiScene:
    scene = str(value or "fallback").strip()
    if scene in VALID_SCENES:
        return scene  # type: ignore[return-value]
    return "fallback"


def _rule_classify(message: str, role: str | None) -> tuple[AiScene, str, float, str]:
    if any(word in message for word in CARPOOL_KEYWORDS):
        return "carpool", "carpool", 0.72, "命中拼车/拼场关键词"
    if any(word in message for word in SCRIPT_RAG_KEYWORDS) or (
        role in {"admin", "manager", "dm"} and any(word in message for word in DM_KEYWORDS)
    ):
        return "script_rag", "script_rag", 0.72, "命中剧本相关关键词"
    if any(word in message for word in RESERVATION_KEYWORDS):
        return "reservation", "reservation", 0.68, "命中预约关键词"
    if message.strip():
        return "store_faq", "store_faq", 0.5, "有明确文本，默认门店客服"
    return "fallback", "fallback", 0.0, "空消息或无法识别"


async def _llm_classify(
    message: str, role: str | None
) -> tuple[AiScene, str, float, str]:
    result = await structured_chat_completion(
        IntentClassification,
        [
            SystemMessage(
                content=(
                    "你是 TableHub 的意图识别器，必须返回符合 schema 的 JSON。"
                    "根据用户消息判断 scene。可选 scene："
                    "carpool=拼车/拼场/组局/缺人；"
                    "script_rag=所有剧本相关问题，包括剧本推荐、内容咨询、角色剧情、任务、线索、机制、复盘真相、DM 开本、带本和剧透控制；"
                    "reservation=预约、报名、价格、时间、余位；"
                    "store_faq=门店规则、地址、停车、退款等客服问题；"
                    "fallback=无法识别。"
                    "JSON 必须包含 scene、intent、confidence、reason 四个字段。"
                )
            ),
            HumanMessage(content=f"用户角色：{role or 'guest'}\n用户消息：{message}"),
        ],
        temperature=0,
        max_tokens=512,
    )
    logger.info("LLM 场景分类结构化结果：%s", result.model_dump())
    scene = _normalize_scene(result.scene)
    return (
        scene,
        result.intent or scene,
        max(0.0, min(result.confidence, 1.0)),
        result.reason or "LLM 结构化意图识别",
    )


async def classify_scene(state: ParentGraphState) -> ParentGraphState:
    message = state.get("message", "").lower()
    role = state.get("role")

    logger.info("进入场景分类节点：role=%s message_length=%s", role or "guest", len(message))
    try:
        scene, intent, confidence, reason = await _llm_classify(message, role)
        logger.info(
            "LLM 场景分类完成：scene=%s intent=%s confidence=%.2f reason=%s",
            scene,
            intent,
            confidence,
            reason,
        )
    except (
        LengthFinishReasonError,
        OpenAIError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        scene, intent, confidence, reason = _rule_classify(message, role)
        logger.warning(
            "LLM 场景分类失败，降级规则分类：error=%s scene=%s intent=%s confidence=%.2f reason=%s",
            exc,
            scene,
            intent,
            confidence,
            reason,
        )
    raw_scene = scene
    raw_intent = intent
    if scene != "fallback" and confidence < INTENT_CONFIDENCE_THRESHOLD:
        scene = "fallback"
        intent = "clarify_intent"
        reason = (
            f"意图置信度 {confidence:.2f} 低于阈值 "
            f"{INTENT_CONFIDENCE_THRESHOLD:.2f}，需要用户补充信息。原判断：{raw_scene}。"
        )
        logger.info(
            "意图置信度过低，转入兜底：raw_scene=%s confidence=%.2f threshold=%.2f",
            raw_scene,
            confidence,
            INTENT_CONFIDENCE_THRESHOLD,
        )
    return {
        **state,
        "scene": scene,
        "intent": intent,
        "intent_confidence": confidence,
        "intent_reason": reason,
        "raw_scene": raw_scene,
        "raw_intent": raw_intent,
    }
