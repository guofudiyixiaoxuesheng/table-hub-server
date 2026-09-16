"""根据门店预约数据派生可运营的玩家行为标签。"""

from __future__ import annotations


def build_behavior_tags(
    *,
    reservation_count: int,
    completed_count: int,
    cancelled_count: int,
    active_count: int,
    estimated_spend_cents: int,
    favorite_genres: list[str],
) -> list[str]:
    """返回有限且稳定的标签，不写回人工维护的 preference 字段。"""

    if reservation_count == 0:
        return ["新玩家"]

    tags: list[str] = []
    if completed_count:
        tags.append(f"已完本{completed_count}次")
    if favorite_genres:
        tags.append(f"偏好·{favorite_genres[0]}")
    if estimated_spend_cents >= 50_000:
        tags.append("高消费")
    elif estimated_spend_cents > 0:
        tags.append("已消费")
    if cancelled_count:
        cancellation_rate = cancelled_count / reservation_count
        tags.append("跳车关注" if cancellation_rate >= 0.3 else "有跳车记录")
    if active_count:
        tags.append("有待到店场次")
    return tags[:5]
