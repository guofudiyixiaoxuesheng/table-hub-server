from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_config
from openai import OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.scenes.reservation.schemas import ReservationQuery
from app.ai.state import ParentGraphState
from app.ai.tools.runtime_context import (
    RelativeDateResolutionError,
    resolve_relative_date,
)
from app.core.store_context import resolve_request_store_id
from app.integrations.llm.client import structured_chat_completion
from app.modules.game_session.models import GameSessionStatus
from app.modules.game_session.service import list_game_sessions

_SELECTION_INDEX_PATTERN = re.compile(r"第\s*([1-9]\d*)\s*(?:车|场|个)")
_CHINESE_SELECTION_INDEX = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_CHINESE_SELECTION_PATTERN = re.compile(r"([一二三四五六七八九十])\s*(?:车|场|个)")
_SESSION_LIST_HEADER_PATTERN = re.compile(r"(\d{1,2})月(\d{1,2})日可(?:拼|预约)场次：")
_SESSION_LIST_ITEM_PATTERN = re.compile(
    r"^\s*(\d+)\.\s*《(.+?)》｜(\d{2}:\d{2})｜余\d+位｜",
    re.MULTILINE,
)


def _resolve_date(
    expression: str | None, time_context: dict[str, object]
) -> date | None:
    if not expression:
        return None

    try:
        return date.fromisoformat(expression)
    except ValueError:
        pass

    now_text = str(time_context.get("now") or "")
    timezone = str(time_context.get("timezone") or "Asia/Shanghai")
    now = datetime.fromisoformat(now_text).astimezone(ZoneInfo(timezone))
    return resolve_relative_date(expression, timezone_name=timezone, now=now)


def _matches_time_period(start_time, period: str, timezone_name: str) -> bool:
    if period == "any":
        return True

    hour = start_time.astimezone(ZoneInfo(timezone_name)).hour
    ranges = {
        "morning": range(6, 12),
        "afternoon": range(12, 18),
        "evening": range(18, 24),
    }
    return hour in ranges[period]


async def _extract_query(
    state: ParentGraphState,
    time_context: dict[str, object],
) -> ReservationQuery:
    return await structured_chat_completion(
        ReservationQuery,
        [
            SystemMessage(
                content=(
                    "你是剧本杀门店咨询条件提取器，只返回符合 schema 的 JSON。"
                    f"当前真实时间上下文：{json.dumps(time_context, ensure_ascii=False)}。"
                    "提取用户想查的日期、时段、人数和剧本关键词。"
                    "不要编造日期；日期不明确时 date_expression 留空，"
                    "needs_clarification=true，并说明需要补充什么。"
                )
            ),
            *[
                HumanMessage(content=item["content"])
                for item in state.get("messages", [])[-8:]
                if item["role"] == "user"
            ],
        ],
        temperature=0,
        max_tokens=400,
    )


def _quick_extract_query(message: str) -> ReservationQuery | None:
    """覆盖高频的场次发现问法，避免“今天有什么本”还要依赖一次 LLM。"""

    date_expression = next(
        (
            expression
            for expression in (
                "今天",
                "明天",
                "后天",
                "今晚",
                "明晚",
                "周一",
                "周二",
                "周三",
                "周四",
                "周五",
                "周六",
                "周日",
                "周天",
                "本周末",
                "下周末",
            )
            if expression in message
        ),
        None,
    )
    if not date_expression:
        return None

    player_count_match = re.search(r"(\d{1,2})\s*(?:个\s*)?(?:人|位)", message)
    player_count = int(player_count_match.group(1)) if player_count_match else None
    time_period = "any"
    if any(word in message for word in ("晚上", "今晚", "夜场", "晚点", "明晚")):
        time_period = "evening"
    elif any(word in message for word in ("下午", "午后")):
        time_period = "afternoon"
    elif any(word in message for word in ("上午", "早上")):
        time_period = "morning"
    return ReservationQuery(
        date_expression=date_expression,
        time_period=time_period,
        player_count=player_count,
    )


def _selected_session_number(message: str) -> int | None:
    match = _SELECTION_INDEX_PATTERN.search(message)
    if match:
        return int(match.group(1))
    chinese_match = _CHINESE_SELECTION_PATTERN.search(message)
    return (
        _CHINESE_SELECTION_INDEX.get(chinese_match.group(1)) if chinese_match else None
    )


def _previous_session_selection(
    messages: list[dict[str, str]],
    selection_number: int,
    time_context: dict[str, object],
) -> tuple[date, str, str] | None:
    """从上一条 AI 场次列表还原被选中的日期、剧本和开始时间。"""

    for item in reversed(messages):
        if item.get("role") != "assistant":
            continue
        content = item.get("content", "")
        header = _SESSION_LIST_HEADER_PATTERN.search(content)
        if not header:
            continue
        target = next(
            (
                match
                for match in _SESSION_LIST_ITEM_PATTERN.finditer(content)
                if int(match.group(1)) == selection_number
            ),
            None,
        )
        if target is None:
            return None
        timezone = ZoneInfo(str(time_context.get("timezone") or "Asia/Shanghai"))
        now = datetime.fromisoformat(str(time_context["now"])).astimezone(timezone)
        target_day = date(now.year, int(header.group(1)), int(header.group(2)))
        return target_day, target.group(2), target.group(3)
    return None


async def _select_previous_session(
    *,
    state: ParentGraphState,
    db: AsyncSession,
    store_id: uuid.UUID,
    time_context: dict[str, object],
    scene_type: str,
) -> ParentGraphState | None:
    selection_number = _selected_session_number(str(state.get("message") or ""))
    if selection_number is None:
        return None
    previous = _previous_session_selection(
        list(state.get("messages") or []), selection_number, time_context
    )
    if previous is None:
        return {
            **state,
            "answer": "我没找到上一轮的场次列表，请重新告诉我想玩的日期，我再帮你查。",
            "next_action": "重新查询可拼场次。",
            "scene_payload": {"type": scene_type, "sessions": []},
        }

    target_day, script_name, start_clock = previous
    timezone_name = str(time_context.get("timezone") or "Asia/Shanghai")
    sessions = await list_game_sessions(
        store_id,
        script_name,
        db,
        day=target_day,
        status=GameSessionStatus.RECRUITING,
    )
    selected = next(
        (
            item
            for item in sessions
            if item.script_name == script_name
            and item.start_time.astimezone(ZoneInfo(timezone_name)).strftime("%H:%M")
            == start_clock
        ),
        None,
    )
    if selected is None:
        return {
            **state,
            "answer": "这场刚刚可能已满员、取消或被调整了。请重新查询当天可拼场次。",
            "next_action": "重新查询可拼场次。",
            "scene_payload": {"type": scene_type, "sessions": []},
        }

    remaining = max(selected.capacity - selected.joined_seats, 0)
    price = f"¥{selected.price_cents / 100:g}" if selected.price_cents else "价格待确认"
    return {
        **state,
        "answer": (
            f"已选第{selection_number}车：《{selected.script_name}》｜"
            f"{start_clock}｜余{remaining}位｜{price}。\n"
            "请告诉我报名人数，我继续帮你登记。"
        ),
        "next_action": "补充报名人数，随后确认玩家信息。",
        "scene_payload": {
            "type": scene_type,
            "selectedSession": {
                "id": str(selected.id),
                "scriptName": selected.script_name,
                "title": selected.title,
                "startTime": selected.start_time.isoformat(),
                "remainingSeats": remaining,
                "priceCents": selected.price_cents,
            },
            "bookingAction": "collect_booking_count",
        },
    }


def _format_session_list(
    candidates: list[dict[str, object]],
    target_day: date,
    *,
    label: str = "可预约场次",
    timezone_name: str = "Asia/Shanghai",
) -> str:
    """明确日期的场次查询直接返回事实列表，避免 LLM 增加无关话术。"""

    lines = [f"{target_day.month}月{target_day.day}日{label}："]
    for index, item in enumerate(candidates, start=1):
        start_time = (
            datetime.fromisoformat(str(item["startTime"]))
            .astimezone(ZoneInfo(timezone_name))
            .strftime("%H:%M")
        )
        price_cents = int(item["priceCents"])
        price = f"¥{price_cents / 100:g}" if price_cents else "价格待确认"
        lines.append(
            f"{index}. 《{item['scriptName']}》｜{start_time}｜余{item['remainingSeats']}位｜{price}"
        )
    return "\n".join(lines)


async def answer_reservation_consultation(
    state: ParentGraphState,
    config: RunnableConfig | None = None,
    *,
    scene_type: str = "reservation",
) -> ParentGraphState:
    try:
        active_config = get_config()
    except RuntimeError:
        active_config = config or {}
    configurable = active_config.get("configurable", {})
    db = configurable.get("db_session")
    store_id_raw = state.get("store_id")
    time_context = dict((state.get("runtime_context") or {}).get("time") or {})

    if not isinstance(db, AsyncSession):
        return {
            **state,
            "answer": "场次查询服务暂不可用，请稍后再试。",
            "next_action": "稍后重试。",
        }

    try:
        requested_store_id = uuid.UUID(str(store_id_raw)) if store_id_raw else None
    except TypeError, ValueError:
        requested_store_id = None
    store_id = await resolve_request_store_id(
        db=db,
        access=None,
        requested_store_id=requested_store_id,
    )
    if store_id is None:
        return {
            **state,
            "answer": "当前还没有可用的门店数据，暂时无法查询场次。",
            "next_action": "请先完成门店初始化。",
        }

    selected_session_response = await _select_previous_session(
        state=state,
        db=db,
        store_id=store_id,
        time_context=time_context,
        scene_type=scene_type,
    )
    if selected_session_response is not None:
        return selected_session_response

    message = str(state.get("rewritten_query") or state.get("message") or "")
    query = _quick_extract_query(message)
    if query is None:
        try:
            query = await _extract_query(state, time_context)
        except OpenAIError:
            return {
                **state,
                "answer": "请告诉我想玩的日期、人数，以及偏好的剧本类型，我来帮你查可拼场次。",
                "next_action": "补充日期、人数或偏好。",
            }

    if query.needs_clarification or not query.date_expression:
        return {
            **state,
            "answer": query.clarification or "你想查哪一天的场次？例如“这周六晚上”。",
            "next_action": "补充日期。",
        }

    try:
        target_day = _resolve_date(query.date_expression, time_context)
    except RelativeDateResolutionError:
        target_day = None

    if not target_day:
        return {
            **state,
            "answer": "我没能确认具体日期。请告诉我类似“这周六”或“2026-09-19”的日期。",
            "next_action": "补充明确日期。",
        }

    sessions = await list_game_sessions(
        store_id,
        query.script_keyword,
        db,
        day=target_day,
        status=GameSessionStatus.RECRUITING,
    )

    timezone = str(time_context.get("timezone") or "Asia/Shanghai")
    candidates = []
    for item in sessions:
        remaining = max(item.capacity - item.joined_seats, 0)
        if query.player_count and remaining < query.player_count:
            continue
        if not _matches_time_period(item.start_time, query.time_period, timezone):
            continue

        candidates.append(
            {
                "id": str(item.id),
                "scriptName": item.script_name,
                "title": item.title,
                "startTime": item.start_time.isoformat(),
                "remainingSeats": remaining,
                "priceCents": item.price_cents,
            }
        )

    if not candidates:
        return {
            **state,
            "answer": "这天暂时没有符合条件的招募场次。你可以换一天、换时段，或告诉我是否接受其他类型的本。",
            "next_action": "调整查询条件或创建约车。",
            "scene_payload": {"type": scene_type, "sessions": []},
        }

    return {
        **state,
        "answer": _format_session_list(
            candidates,
            target_day,
            label="可拼场次" if scene_type == "carpool" else "可预约场次",
            timezone_name=timezone,
        ),
        "next_action": "回复场次序号可查看详情或报名。",
        "scene_payload": {
            "type": scene_type,
            "sessions": candidates,
            "bookingAction": "select_session",
        },
    }
