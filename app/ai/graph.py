"""AI 对话总入口父图。

设计原则：
1. 前端 AI 对话只打这个父图入口。
2. 父图只做场景识别、公共预处理和分流。
3. DM 开本、预约、客服 RAG 后续作为子图挂载，避免业务堆在一个函数里。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.ai.nodes.classify import classify_scene
from app.ai.nodes.handlers import (
    carpool_handler,
    casual_chat_handler,
    fallback_handler,
    reservation_handler,
    script_rag_handler,
    store_faq_handler,
)
from app.ai.nodes.rewrite import rewrite_query
from app.ai.nodes.routes import route_scene
from app.ai.state import ParentGraphState


def build_parent_graph(checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(ParentGraphState)
    graph.add_node("classify_scene", classify_scene)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("carpool_handler", carpool_handler)
    graph.add_node("script_rag_handler", script_rag_handler)
    graph.add_node("reservation_handler", reservation_handler)
    graph.add_node("store_faq_handler", store_faq_handler)
    graph.add_node("casual_chat_handler", casual_chat_handler)
    graph.add_node("fallback_handler", fallback_handler)

    graph.add_edge(START, "classify_scene")
    graph.add_edge("classify_scene", "rewrite_query")
    graph.add_conditional_edges(
        "rewrite_query",
        route_scene,
        {
            "carpool": "carpool_handler",
            "script_rag": "script_rag_handler",
            "reservation": "reservation_handler",
            "store_faq": "store_faq_handler",
            "casual_chat": "casual_chat_handler",
            "fallback": "fallback_handler",
        },
    )
    graph.add_edge("carpool_handler", END)
    graph.add_edge("script_rag_handler", END)
    graph.add_edge("reservation_handler", END)
    graph.add_edge("store_faq_handler", END)
    graph.add_edge("casual_chat_handler", END)
    graph.add_edge("fallback_handler", END)
    return graph.compile(checkpointer=checkpointer)


async def run_parent_graph(
    graph,
    state: ParentGraphState,
    thread_id: str,
    callbacks: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
    run_name: str | None = None,
    **configurable: Any,
) -> ParentGraphState:
    return await graph.ainvoke(
        state,
        config={
            "configurable": {"thread_id": thread_id, **configurable},
            "callbacks": callbacks or [],
            "metadata": metadata or {},
            "run_name": run_name or "tablehub-parent-graph",
        },
    )


async def stream_parent_graph(
    graph,
    state: ParentGraphState,
    thread_id: str,
    stream_mode: Literal["updates", "values"] = "updates",
    callbacks: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
    run_name: str | None = None,
    **configurable: Any,
) -> AsyncIterator[Any]:
    graph_stream_mode: Any = (
        ["updates", "custom"] if stream_mode == "updates" else stream_mode
    )
    async for event in graph.astream(
        state,
        config={
            "configurable": {"thread_id": thread_id, **configurable},
            "callbacks": callbacks or [],
            "metadata": metadata or {},
            "run_name": run_name or "tablehub-parent-graph-stream",
        },
        stream_mode=graph_stream_mode,
        subgraphs=True,
    ):
        yield event
