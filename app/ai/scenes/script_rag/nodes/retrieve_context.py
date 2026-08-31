"""剧本 RAG 检索节点。"""

from __future__ import annotations

from app.ai.scenes.script_rag.state import ScriptRagState


async def retrieve_script_context(state: ScriptRagState) -> ScriptRagState:
    """预留检索节点。

    下一步会在这里接入现有 hybrid retriever，并按剧本、幕、角色、权限过滤。
    """

    return {
        **state,
        "retrieved_chunks": [],
        "safe_context": "",
    }
