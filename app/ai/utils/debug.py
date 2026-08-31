"""轻量级 LangGraph state/context 打印工具。

开发 LangGraph 时，直接 ``print(state)`` 很容易把 messages、chunks、
markdown 等大字段全部打出来，日志会非常难读。

这个模块只做一件事：
把常用关键信息按模块整理后打印，并自动隐藏/截断大字段。

用法：

    from app.ai.utils import debug_state

    debug_state("retrieve_script_context:input", state)

如果你只是想临时打印某个普通 dict，也可以使用：

    debug_context("oss_complete", {"file_count": 12, "status": "ok"})
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

DEFAULT_MAX_TEXT_LENGTH = 300


SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def _is_sensitive_key(key: str) -> bool:
    """判断字段名是否像敏感信息。

    这里故意做模糊匹配，避免把 token/password 之类内容打进日志。
    """

    lower_key = key.lower()
    return any(sensitive_key in lower_key for sensitive_key in SENSITIVE_KEYS)


def _short_text(value: str, max_length: int = DEFAULT_MAX_TEXT_LENGTH) -> str:
    """截断长文本，避免 markdown/chunk/message 把日志刷爆。"""

    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}... <truncated {len(value) - max_length} chars>"


def _safe_value(value: Any, *, max_length: int = DEFAULT_MAX_TEXT_LENGTH) -> Any:
    """把复杂对象转成适合打印的轻量值。

    - 字符串：保留短文本，长文本截断
    - list/tuple：只打印长度，不展开内容
    - dict：只打印长度，不展开内容
    - 日期/UUID/Decimal：转成字符串
    """

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        return _short_text(value, max_length=max_length)

    if isinstance(value, UUID | datetime | date | Decimal):
        return str(value)

    if isinstance(value, Mapping):
        return f"dict[{len(value)}]"

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return f"list[{len(value)}]"

    return str(value)


def _count(value: Any) -> int:
    """安全计算列表/字典数量，字段不存在时返回 0。"""

    if isinstance(value, Mapping | Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value)
    return 0


def pick_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """从 LangGraph state 中挑选最常看的字段。

    注意：
    这里不是完整 dump，而是调试视角的摘要。
    真正线上可观测后续会走 trace/span，不建议长期依赖 print。
    """

    return {
        "input": {
            "message": _safe_value(state.get("message")),
            "rewritten_query": _safe_value(state.get("rewritten_query")),
            "context_rewritten_query": _safe_value(state.get("context_rewritten_query")),
            "messages_count": _count(state.get("messages")),
        },
        "user": {
            "user_id": _safe_value(state.get("user_id")),
            "store_id": _safe_value(state.get("store_id")),
            "role": _safe_value(state.get("role")),
        },
        "intent": {
            "scene": _safe_value(state.get("scene")),
            "intent": _safe_value(state.get("intent")),
            "confidence": _safe_value(state.get("intent_confidence")),
            "reason": _safe_value(state.get("intent_reason")),
            "raw_scene": _safe_value(state.get("raw_scene")),
            "raw_intent": _safe_value(state.get("raw_intent")),
        },
        "script": {
            "script_name": _safe_value(state.get("script_name")),
            "act": _safe_value(state.get("act")),
            "role_name": _safe_value(state.get("role_name")),
            "question_type": _safe_value(state.get("question_type")),
            "permission_level": _safe_value(state.get("permission_level")),
            "spoiler_risk": _safe_value(state.get("spoiler_risk")),
        },
        "retrieval": {
            "retrieved_count": _count(state.get("retrieved_chunks")),
            "citations_count": _count(state.get("citations")),
            "safe_context_length": len(state.get("safe_context") or ""),
        },
        "output": {
            "answer": _safe_value(state.get("answer")),
            "next_action": _safe_value(state.get("next_action")),
        },
        "payload": {
            "scene_payload": _safe_value(state.get("scene_payload")),
        },
    }


def sanitize_context(context: Mapping[str, Any], *, max_length: int = DEFAULT_MAX_TEXT_LENGTH) -> dict[str, Any]:
    """清洗普通 context，适合打印接口入参、OSS 回调、检索参数等。"""

    result: dict[str, Any] = {}
    for key, value in context.items():
        if _is_sensitive_key(key):
            result[key] = "***"
            continue
        result[key] = _safe_value(value, max_length=max_length)
    return result


def debug_context(title: str, context: Mapping[str, Any], *, enabled: bool = True) -> None:
    """结构化打印普通上下文。

    ``enabled`` 方便你临时关闭某个节点调试，不用删代码。
    """

    if not enabled:
        return

    _print_debug_block(title, sanitize_context(context))


def debug_state(title: str, state: Mapping[str, Any], *, enabled: bool = True) -> None:
    """结构化打印 LangGraph state 摘要。

    推荐在节点入口/出口使用：

        debug_state("parse_script_question:input", state)
        debug_state("parse_script_question:output", {**state, **result})
    """

    if not enabled:
        return

    _print_debug_block(title, pick_state(state))


def _print_debug_block(title: str, payload: Mapping[str, Any]) -> None:
    """统一输出格式，方便在终端里搜索节点名。"""

    print(
        f"\n===== {title} =====\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        + f"\n===== END {title} =====\n",
        flush=True,
    )
