"""剧本 RAG 检索节点。"""

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.ai.scenes.script_rag.state import ScriptRagState
from app.ai.utils import debug_context, debug_state
from app.modules.knowledge.actions.retrieve_chunks import KnowledgeRetriever
from app.modules.knowledge.actions.search_documents import find_active_script_document
from app.modules.knowledge.schemas import KnowledgeRetrieveRequest

MAX_SAFE_CONTEXT_CHARS = 6000


def _get_configurable(config: RunnableConfig | None) -> dict[str, Any]:
    if not config:
        return {}
    configurable = config.get("configurable")
    return configurable if isinstance(configurable, dict) else {}


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _retrieval_payload(state: ScriptRagState, query: str) -> KnowledgeRetrieveRequest:
    """把子图 state 转成知识库检索器入参。"""

    permission_level = state.get("permission_level")
    role_name = state.get("role_name")
    act = state.get("act")

    # DM/店长/管理员可以按幕或角色定向检索；普通玩家只在明确角色时加角色过滤。
    # 后续如果引入 chunk visibility，可在这里继续补权限过滤。
    return KnowledgeRetrieveRequest(
        query=query,
        topK=8,
        mode="hybrid",
        roleName=role_name if permission_level in {"player", "dm", "manager", "admin"} else None,
        act=act,
    )


def _chunks_to_state(results: list[Any]) -> list[dict[str, object]]:
    return [
        {
            "chunk_id": str(item.chunk_id),
            "file_id": str(item.file_id),
            "relative_path": item.relative_path,
            "title": item.title,
            "act": item.act,
            "role_name": item.role_name,
            "chunk_type": item.chunk_type,
            "content": item.content,
            "score": item.score,
            "score_type": item.score_type,
        }
        for item in results
    ]


def _build_safe_context(chunks: list[dict[str, object]]) -> str:
    """把召回 chunk 拼成给回答节点使用的上下文，控制长度避免 prompt 爆炸。"""

    blocks: list[str] = []
    total = 0
    for index, chunk in enumerate(chunks, start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        header = (
            f"[{index}] 文件：{chunk.get('relative_path') or '未知'}"
            f"｜标题：{chunk.get('title') or '无'}"
            f"｜幕次：{chunk.get('act') or '无'}"
            f"｜角色：{chunk.get('role_name') or '无'}"
        )
        block = f"{header}\n{content}"
        if total + len(block) > MAX_SAFE_CONTEXT_CHARS:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n---\n\n".join(blocks)


def _build_citations(chunks: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "chunkId": chunk["chunk_id"],
            "fileId": chunk["file_id"],
            "relativePath": chunk["relative_path"],
            "title": chunk.get("title"),
            "act": chunk.get("act"),
            "roleName": chunk.get("role_name"),
            "chunkType": chunk.get("chunk_type"),
            "score": chunk.get("score"),
            "scoreType": chunk.get("score_type"),
        }
        for chunk in chunks
    ]


async def retrieve_script_context(
    state: ScriptRagState, config: RunnableConfig | None = None
) -> ScriptRagState:
    """剧本 RAG 召回节点。

    这里是真正调用知识库检索器的位置：
    context_rewritten_query -> hybrid(BM25 + vector + RRF + rerank) -> chunks。
    """
    debug_state("retrieve_script_context:input", state)

    query = state.get("context_rewritten_query") or state.get("rewritten_query") or state.get("message") or ""
    store_id = _parse_uuid(state.get("store_id"))
    db = _get_configurable(config).get("db_session")
    debug_context(
        "retrieve_script_context:query",
        {
            "query": query,
            "allowed_filters": state.get("allowed_filters") or {},
            "store_id": state.get("store_id"),
        },
    )

    if not query.strip():
        return {
            **state,
            "retrieved_chunks": [],
            "safe_context": "",
            "citations": [],
            "next_action": "缺少可检索的问题。",
        }
    if store_id is None:
        return {
            **state,
            "retrieved_chunks": [],
            "safe_context": "",
            "citations": [],
            "next_action": "缺少门店上下文，无法定位剧本知识库。",
        }
    if not hasattr(db, "execute") or not hasattr(db, "scalar"):
        return {
            **state,
            "retrieved_chunks": [],
            "safe_context": "",
            "citations": [],
            "next_action": "缺少数据库会话，无法执行剧本 RAG 检索。",
        }

    document_version = await find_active_script_document(
        store_id=store_id,
        script_name=state.get("script_name"),
        db=db,  # type: ignore[arg-type]
    )
    if document_version is None:
        return {
            **state,
            "retrieved_chunks": [],
            "safe_context": "",
            "citations": [],
            "next_action": "没有找到可用的剧本知识库，请先上传、加载、切片并向量化。",
        }

    document, version = document_version
    payload = _retrieval_payload(state, query)
    response = await KnowledgeRetriever(db).retrieve(  # type: ignore[arg-type]
        document_id=document.id,
        version_id=version.id,
        store_id=store_id,
        payload=payload,
    )
    chunks = _chunks_to_state(response.results)
    safe_context = _build_safe_context(chunks)
    citations = _build_citations(chunks)

    debug_context(
        "retrieve_script_context:result",
        {
            "document_id": document.id,
            "document_name": document.name,
            "version_id": version.id,
            "query": response.query,
            "mode": response.mode,
            "retrieved_count": len(chunks),
            "safe_context_length": len(safe_context),
        },
    )

    return {
        **state,
        "script_id": str(document.id),
        "script_name": state.get("script_name") or document.name,
        "retrieved_chunks": chunks,
        "safe_context": safe_context,
        "citations": citations,
        "next_action": "剧本 RAG 召回完成，进入回答生成。",
    }
