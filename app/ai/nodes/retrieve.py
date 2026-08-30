"""父图检索节点占位。"""

from __future__ import annotations

from app.ai.state import ParentGraphState


def retrieve_context(state: ParentGraphState) -> ParentGraphState:
    # 后续这里接 KnowledgeRetriever：BM25 / Vector / RRF / Rerank。
    return {**state, "citations": []}
