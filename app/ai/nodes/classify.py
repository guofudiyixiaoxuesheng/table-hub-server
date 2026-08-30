"""父图入口分类节点。"""

from __future__ import annotations

from app.ai.state import AiScene, ParentGraphState

DM_KEYWORDS = ("dm", "主持", "开本", "带本", "复盘", "幕", "线索", "凶手", "剧透")
RESERVATION_KEYWORDS = ("预约", "报名", "场次", "几点", "周末", "价格", "余位", "拼车")


def classify_scene(state: ParentGraphState) -> ParentGraphState:
    message = state.get("message", "").lower()
    role = state.get("role")

    scene: AiScene
    if role in {"admin", "manager", "dm"} and any(word in message for word in DM_KEYWORDS):
        scene = "dm_opening"
    elif any(word in message for word in RESERVATION_KEYWORDS):
        scene = "reservation"
    elif message.strip():
        scene = "customer_service"
    else:
        scene = "fallback"

    return {**state, "scene": scene}
