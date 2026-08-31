"""计算剧本 RAG 权限和过滤条件。"""

from __future__ import annotations

from app.ai.scenes.script_rag.state import ScriptPermissionLevel, ScriptRagState


def _permission_level(role: str | None) -> ScriptPermissionLevel:
    if role == "admin":
        return "admin"
    if role == "manager":
        return "manager"
    if role == "dm":
        return "dm"
    if role == "user":
        return "player"
    return "guest"


def check_permission(state: ScriptRagState) -> ScriptRagState:
    permission_level = _permission_level(state.get("role"))
    allowed_filters: dict[str, object] = {
        "resource_type": "script",
        "script_name": state.get("script_name"),
        "act": state.get("act"),
        "role_name": state.get("role_name"),
        "permission_level": permission_level,
    }
    return {
        **state,
        "permission_level": permission_level,
        "allowed_filters": allowed_filters,
    }
