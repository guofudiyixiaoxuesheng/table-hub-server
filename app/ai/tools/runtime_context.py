"""不依赖外部网络的运行时上下文工具。

模型不能可靠感知当前日期和时区；这些函数把可验证的时间事实提供给
预约、拼车等业务流程。自然语言理解仍由上游 LLM 完成，本模块只处理
已识别出的相对日期表达。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

_WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_WEEKDAY_ALIASES = {
    "周一": 0,
    "星期一": 0,
    "礼拜一": 0,
    "周二": 1,
    "星期二": 1,
    "礼拜二": 1,
    "周三": 2,
    "星期三": 2,
    "礼拜三": 2,
    "周四": 3,
    "星期四": 3,
    "礼拜四": 3,
    "周五": 4,
    "星期五": 4,
    "礼拜五": 4,
    "周六": 5,
    "星期六": 5,
    "礼拜六": 5,
    "周日": 6,
    "周天": 6,
    "星期日": 6,
    "星期天": 6,
    "礼拜日": 6,
}


class RelativeDateResolutionError(ValueError):
    """相对日期表达不在当前基础工具支持范围内。"""


def _timezone(value: str | None = None) -> ZoneInfo:
    name = value or settings.AI_DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RelativeDateResolutionError(f"不支持的时区：{name}") from exc


def current_datetime(timezone_name: str | None = None) -> datetime:
    """获取指定业务时区下的当前时间。"""

    return datetime.now(_timezone(timezone_name))


def build_time_context(
    *,
    timezone_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, str | int]:
    """生成可直接附加给 LLM 的、可验证的当前时间上下文。"""

    timezone = _timezone(timezone_name)
    local_now = now.astimezone(timezone) if now else datetime.now(timezone)
    return {
        "timezone": str(timezone),
        "now": local_now.isoformat(timespec="minutes"),
        "today": local_now.date().isoformat(),
        "weekday": local_now.weekday(),
        "weekdayName": _WEEKDAY_NAMES[local_now.weekday()],
    }


def resolve_relative_date(
    expression: str,
    *,
    timezone_name: str | None = None,
    now: datetime | None = None,
) -> date:
    """将常见中文相对日期解析成确定日期。

    ``周六`` 默认指今天起最近一次周六；``下周六`` 指下一个自然周的周六。
    如果需要处理模糊的“过两天”“月底”等表达，应交给上游抽取器追问，
    而不是在这里猜测。
    """

    value = expression.strip().replace(" ", "")
    if not value:
        raise RelativeDateResolutionError("日期表达不能为空")

    timezone = _timezone(timezone_name)
    local_now = now.astimezone(timezone) if now else datetime.now(timezone)
    today = local_now.date()
    direct = {"今天": 0, "明天": 1, "后天": 2}
    if value in direct:
        return today + timedelta(days=direct[value])

    if value in {"这周末", "本周末", "这个周末"}:
        return today + timedelta(days=5 - today.weekday())
    if value in {"下周末", "下个周末"}:
        return today + timedelta(days=(5 - today.weekday()) % 7 + 7)

    prefix = ""
    weekday_text = value
    if value.startswith(("下周", "下星期", "下礼拜")):
        prefix = "next"
        weekday_text = value[2:] if value.startswith("下周") else value[3:]
    elif value.startswith(("本周", "这周", "这星期", "本星期", "这礼拜", "本礼拜")):
        prefix = "this"
        weekday_text = value[2:] if value.startswith(("本周", "这周")) else value[3:]

    if weekday_text in "一二三四五六日天":
        weekday_text = f"周{weekday_text}"
    target_weekday = _WEEKDAY_ALIASES.get(weekday_text)
    if target_weekday is None:
        raise RelativeDateResolutionError(f"暂不支持的相对日期：{expression}")

    days_until = (target_weekday - today.weekday()) % 7
    if prefix == "next":
        return today + timedelta(days=days_until + 7)
    if prefix == "this":
        return today + timedelta(days=target_weekday - today.weekday())
    return today + timedelta(days=days_until)
