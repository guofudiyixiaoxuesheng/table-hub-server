"""父图查询改写节点。"""

from __future__ import annotations

from app.ai.state import ParentGraphState


def rewrite_query(state: ParentGraphState) -> ParentGraphState:
    # MVP 先保持原问题；后续这里可结合历史消息改写成独立检索 query。
    return {**state, "rewritten_query": state.get("message", "").strip()}
