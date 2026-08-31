"""剧本相关 RAG 子图。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.ai.scenes.script_rag.nodes.check_permission import check_permission
from app.ai.scenes.script_rag.nodes.fallback import missing_info_fallback, spoiler_block
from app.ai.scenes.script_rag.nodes.generate_answer import generate_script_answer
from app.ai.scenes.script_rag.nodes.parse_question import parse_script_question
from app.ai.scenes.script_rag.nodes.retrieve_context import retrieve_script_context
from app.ai.scenes.script_rag.nodes.validate_answer import validate_script_answer
from app.ai.scenes.script_rag.routes import route_script_question
from app.ai.scenes.script_rag.state import ScriptRagState


def build_script_rag_graph():
    graph = StateGraph(ScriptRagState)
    graph.add_node("parse_script_question", parse_script_question)
    graph.add_node("check_permission", check_permission)
    graph.add_node("retrieve_context", retrieve_script_context)
    graph.add_node("generate_answer", generate_script_answer)
    graph.add_node("validate_answer", validate_script_answer)
    graph.add_node("missing_info", missing_info_fallback)
    graph.add_node("spoiler_block", spoiler_block)

    graph.add_edge(START, "parse_script_question")
    graph.add_edge("parse_script_question", "check_permission")
    graph.add_conditional_edges(
        "check_permission",
        route_script_question,
        {
            "missing_info": "missing_info",
            "spoiler_block": "spoiler_block",
            "retrieve_context": "retrieve_context",
        },
    )
    graph.add_edge("retrieve_context", "generate_answer")
    graph.add_edge("generate_answer", "validate_answer")
    graph.add_edge("validate_answer", END)
    graph.add_edge("missing_info", END)
    graph.add_edge("spoiler_block", END)
    return graph.compile()
