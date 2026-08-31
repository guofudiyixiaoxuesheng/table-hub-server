"""父图回答生成节点。"""

from __future__ import annotations

from app.ai.state import ParentGraphState


def generate_answer(state: ParentGraphState) -> ParentGraphState:
    scene = state.get("scene", "fallback")
    query = state.get("rewritten_query") or state.get("message", "")

    scene_labels = {
        "carpool": "拼车助手",
        "script_consulting": "剧本咨询",
        "dm_opening": "DM 开本助手",
        "reservation": "预约咨询",
        "customer_service": "门店客服",
        "fallback": "兜底助手",
    }
    next_actions = {
        "carpool": "后续接拼车子图：按人数、时间、剧本偏好匹配可拼场次。",
        "script_consulting": "后续接剧本咨询 RAG：按人数、类型、时长、难度和禁忌做推荐。",
        "dm_opening": "后续接 DM 子图：角色权限判断、按幕检索、剧透控制、开本话术生成。",
        "reservation": "后续接预约子图：场次查询、人数判断、预约码生成。",
        "customer_service": "后续接客服 RAG：知识库召回、精排、引用回答。",
        "fallback": "等待用户补充更明确的问题。",
    }

    if scene == "fallback" and state.get("intent") == "clarify_intent":
        answer = (
            f"我有点不确定你具体想做哪类操作。\n"
            f"当前问题：{query or '暂无'}\n"
            f"原始判断：{state.get('raw_scene', 'unknown')}，置信度 {state.get('intent_confidence', 0):.2f}\n"
            "你可以补充一下：是想拼车/拼场、咨询剧本、预约场次，还是 DM 开本？"
        )
    else:
        answer = (
            f"已进入【{scene_labels.get(scene, '兜底助手')}】父图分支。\n"
            f"当前问题：{query or '暂无'}\n"
            f"识别意图：{state.get('intent', scene)}（置信度 {state.get('intent_confidence', 0):.2f}）\n"
            f"下一步：{next_actions.get(scene, next_actions['fallback'])}"
        )
    return {**state, "answer": answer, "next_action": next_actions.get(scene, "")}
