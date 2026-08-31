"""剧本 RAG 子图内部条件路由。"""

from __future__ import annotations

from typing import Literal

from app.ai.scenes.script_rag.state import ScriptRagState

ScriptRagRoute = Literal["missing_info", "spoiler_block", "retrieve_context"]


def route_script_question(state: ScriptRagState) -> ScriptRagRoute:
    """按信息完整度、权限和剧透风险选择处理路径。"""

    if state.get("question_type") == "missing_info":
        return "missing_info"
    if state.get("spoiler_risk") == "high" and state.get("permission_level") in {
        "guest",
        "player",
    }:
        return "spoiler_block"
    return "retrieve_context"
