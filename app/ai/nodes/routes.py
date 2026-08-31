"""父图条件路由函数。"""

from __future__ import annotations

from typing import Literal

from app.ai.state import ParentGraphState

RouteName = Literal[
    "carpool",
    "script_rag",
    "reservation",
    "store_faq",
    "fallback",
]


def route_scene(state: ParentGraphState) -> RouteName:
    """根据意图识别结果选择后续业务分支。"""

    scene = state.get("scene", "fallback")
    if scene in {
        "carpool",
        "script_rag",
        "reservation",
        "store_faq",
    }:
        return scene
    return "fallback"
