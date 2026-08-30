"""父图回答生成节点。"""

from __future__ import annotations

from app.ai.state import ParentGraphState


def generate_answer(state: ParentGraphState) -> ParentGraphState:
    scene = state.get("scene", "fallback")
    query = state.get("rewritten_query") or state.get("message", "")

    scene_labels = {
        "dm_opening": "DM 开本助手",
        "reservation": "预约咨询",
        "customer_service": "门店客服",
        "fallback": "兜底助手",
    }
    next_actions = {
        "dm_opening": "后续接 DM 子图：角色权限判断、按幕检索、剧透控制、开本话术生成。",
        "reservation": "后续接预约子图：场次查询、人数判断、预约码生成。",
        "customer_service": "后续接客服 RAG：知识库召回、精排、引用回答。",
        "fallback": "等待用户补充更明确的问题。",
    }

    answer = (
        f"已进入【{scene_labels.get(scene, '兜底助手')}】父图分支。\n"
        f"当前问题：{query or '暂无'}\n"
        f"下一步：{next_actions.get(scene, next_actions['fallback'])}"
    )
    return {**state, "answer": answer, "next_action": next_actions.get(scene, "")}
