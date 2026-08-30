"""父图精排节点占位。"""

from __future__ import annotations

from app.ai.state import ParentGraphState


def rerank_context(state: ParentGraphState) -> ParentGraphState:
    # 后续可以把 app.modules.knowledge.actions.retrieve_chunks.rerank_results 接进来。
    return state
