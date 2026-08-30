"""AI 对话总入口父图。

设计原则：
1. 前端 AI 对话只打这个父图入口。
2. 父图只做场景识别、公共预处理和分流。
3. DM 开本、预约、客服 RAG 后续作为子图挂载，避免业务堆在一个函数里。
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.ai.nodes.classify import classify_scene
from app.ai.nodes.generate import generate_answer
from app.ai.nodes.rerank import rerank_context
from app.ai.nodes.retrieve import retrieve_context
from app.ai.nodes.rewrite import rewrite_query
from app.ai.state import ParentGraphState


def build_parent_graph(checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(ParentGraphState)
    graph.add_node("classify_scene", classify_scene)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("rerank_context", rerank_context)
    graph.add_node("generate_answer", generate_answer)

    graph.add_edge(START, "classify_scene")
    graph.add_edge("classify_scene", "rewrite_query")
    graph.add_edge("rewrite_query", "retrieve_context")
    graph.add_edge("retrieve_context", "rerank_context")
    graph.add_edge("rerank_context", "generate_answer")
    graph.add_edge("generate_answer", END)
    return graph.compile(checkpointer=checkpointer)


async def run_parent_graph(graph, state: ParentGraphState, thread_id: str) -> ParentGraphState:
    return await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": thread_id}},
    )
