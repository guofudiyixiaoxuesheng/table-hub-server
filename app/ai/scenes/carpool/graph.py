from langgraph.graph import END, START, StateGraph

from app.ai.state import ParentGraphState
from app.api.v1.game_sessions import list_sessions


async def query_sessions(state: ParentGraphState):
    print("query_sessions~~~~~~~~", state)
    res = await list_sessions()
    return res


# def query_
def build_carpool_graph():
    """构建 RAG 子图。"""
    graph = StateGraph(ParentGraphState)
    # graph.add_node(START, query_sessions)
    graph.add_node("query_sessions", query_sessions)
    # graph.add_node(END, END)
    graph.add_edge(START, "query_sessions")
    graph.add_edge("query_sessions", END)
    return graph.compile()
