"""LangGraph 父图共享状态。

父图只负责识别入口场景和调度子流程；具体 DM 开本、预约、客服 RAG
后续都可以拆成独立子图挂进来。
"""

from __future__ import annotations

from typing import Literal, TypedDict

AiScene = Literal["dm_opening", "reservation", "customer_service", "fallback"]


class AiMessage(TypedDict):
    role: Literal["user", "assistant", "system", "tool"]
    content: str


class ParentGraphState(TypedDict, total=False):
    user_id: str | None
    store_id: str | None
    role: str | None
    message: str
    messages: list[AiMessage]
    scene: AiScene
    rewritten_query: str
    answer: str
    citations: list[dict[str, object]]
    next_action: str
