"""基于现有预约和场次数据生成玩家行为分析。"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.game_session.models import GameSession, GameSessionStatus, SessionPlayer, SessionPlayerStatus
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.user.actions.manage_store_players import StorePlayerNotFoundError, _to_store_player_response
from app.modules.user.models import StorePlayer, User, UserRole, UserStatus
from app.modules.user.schemas import (
    PlayerBehaviorSummaryResponse,
    PlayerSessionBehaviorItem,
    StorePlayerAnalyticsResponse,
)

SCRIPT_GENRE_LABELS = {
    "mystery_hardcore": "推理本/硬核本",
    "honkaku": "本格本",
    "henkaku": "变格本",
    "restoration": "还原本",
    "emotional": "情感本",
    "mechanism": "机制本",
    "faction": "阵营本",
    "comedy": "欢乐本",
    "horror": "恐怖本",
}


def _genre_label(value: object) -> str:
    if value is None:
        return "未分类"
    genre_value = getattr(value, "value", str(value))
    return SCRIPT_GENRE_LABELS.get(genre_value, genre_value)


def _cancellation_rate(cancelled_count: int, reservation_count: int) -> float:
    if reservation_count <= 0:
        return 0
    return round(cancelled_count / reservation_count, 4)


async def get_player_behavior_summary(
    store_id: uuid.UUID,
    store_player_id: uuid.UUID,
    db: AsyncSession,
) -> PlayerBehaviorSummaryResponse:
    row = (
        await db.execute(
            select(StorePlayer, User)
            .join(User, User.id == StorePlayer.user_id)
            .where(
                StorePlayer.id == store_player_id,
                StorePlayer.store_id == store_id,
                StorePlayer.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
        )
    ).tuples().first()
    if row is None:
        raise StorePlayerNotFoundError("玩家不存在")

    store_player, user = row
    session_rows = (
        await db.execute(
            select(SessionPlayer, GameSession, KnowledgeDocument)
            .join(GameSession, GameSession.id == SessionPlayer.session_id)
            .outerjoin(KnowledgeDocument, KnowledgeDocument.id == GameSession.script_document_id)
            .where(
                GameSession.store_id == store_id,
                GameSession.deleted_at.is_(None),
                SessionPlayer.user_id == user.id,
            )
            .order_by(SessionPlayer.created_at.desc())
        )
    ).tuples().all()

    reservation_count = len(session_rows)
    cancelled_count = sum(1 for player, _, _ in session_rows if player.status == SessionPlayerStatus.CANCELLED)
    active_count = reservation_count - cancelled_count
    completed_count = sum(
        1
        for player, session, _ in session_rows
        if player.status != SessionPlayerStatus.CANCELLED and session.status == GameSessionStatus.COMPLETED
    )
    estimated_spend = sum(
        session.price_cents * player.seat_count
        for player, session, _ in session_rows
        if player.status != SessionPlayerStatus.CANCELLED and session.status == GameSessionStatus.COMPLETED
    )
    genre_counter = Counter(
        _genre_label(doc.script_genre)
        for player, _, doc in session_rows
        if player.status != SessionPlayerStatus.CANCELLED and doc is not None
    )
    favorite_genres = [item for item, _ in genre_counter.most_common(3)]
    recent_sessions = [
        PlayerSessionBehaviorItem(
            session_id=session.id,
            title=session.title,
            script_name=session.script_name,
            script_genre=_genre_label(doc.script_genre) if doc else None,
            start_time=session.start_time,
            duration_minutes=session.duration_minutes,
            capacity=session.capacity,
            joined_seats=session.joined_seats,
            price_cents=session.price_cents,
            cover_image_url=session.cover_image_url,
            join_status=player.status.value,
            reservation_code=player.reservation_code,
            source=player.source.value,
            seat_count=player.seat_count,
            joined_at=player.created_at,
            updated_at=player.updated_at,
        )
        for player, session, doc in session_rows[:10]
    ]
    ai_summary = (
        f"该玩家累计预约 {reservation_count} 次，完成体验 {completed_count} 次，取消 {cancelled_count} 次。"
        f"偏好类型集中在 {('、'.join(favorite_genres) if favorite_genres else '暂无明显偏好')}。"
    )

    return PlayerBehaviorSummaryResponse(
        store_player=_to_store_player_response((store_player, user)),
        reservation_count=reservation_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count,
        active_reservation_count=active_count,
        cancellation_rate=_cancellation_rate(cancelled_count, reservation_count),
        estimated_spend_cents=estimated_spend,
        favorite_genres=favorite_genres,
        recent_sessions=recent_sessions,
        ai_summary=ai_summary,
    )


async def get_current_player_behavior_summary(
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> PlayerBehaviorSummaryResponse:
    store_player_id = await db.scalar(
        select(StorePlayer.id).where(
            StorePlayer.store_id == store_id,
            StorePlayer.user_id == user_id,
            StorePlayer.deleted_at.is_(None),
        )
    )
    if store_player_id is None:
        raise StorePlayerNotFoundError("当前账号还没有拼车记录")
    return await get_player_behavior_summary(store_id, store_player_id, db)


async def get_store_player_analytics(
    store_id: uuid.UUID,
    db: AsyncSession,
) -> StorePlayerAnalyticsResponse:
    total_players = await db.scalar(
        select(func.count())
        .select_from(StorePlayer)
        .join(User, User.id == StorePlayer.user_id)
        .where(
            StorePlayer.store_id == store_id,
            StorePlayer.deleted_at.is_(None),
            User.role == UserRole.USER,
            User.status != UserStatus.DISABLED,
            User.deleted_at.is_(None),
        )
    )
    rows = (
        await db.execute(
            select(SessionPlayer, GameSession, KnowledgeDocument, User)
            .join(GameSession, GameSession.id == SessionPlayer.session_id)
            .outerjoin(KnowledgeDocument, KnowledgeDocument.id == GameSession.script_document_id)
            .outerjoin(User, User.id == SessionPlayer.user_id)
            .where(GameSession.store_id == store_id, GameSession.deleted_at.is_(None))
            .order_by(SessionPlayer.created_at.desc())
        )
    ).tuples().all()

    reservation_count = len(rows)
    cancelled_count = sum(1 for player, _, _, _ in rows if player.status == SessionPlayerStatus.CANCELLED)
    active_count = reservation_count - cancelled_count
    completed_count = sum(
        1
        for player, session, _, _ in rows
        if player.status != SessionPlayerStatus.CANCELLED and session.status == GameSessionStatus.COMPLETED
    )
    estimated_revenue = sum(
        session.price_cents * player.seat_count
        for player, session, _, _ in rows
        if player.status != SessionPlayerStatus.CANCELLED and session.status == GameSessionStatus.COMPLETED
    )

    genre_counter = Counter(
        _genre_label(doc.script_genre)
        for player, _, doc, _ in rows
        if player.status != SessionPlayerStatus.CANCELLED and doc is not None
    )
    player_stats: dict[str, dict[str, object]] = defaultdict(lambda: {
        "reservationCount": 0,
        "cancelledCount": 0,
        "completedCount": 0,
        "nickname": "未命名玩家",
        "phone": None,
    })
    for player, session, _, user in rows:
        key = str(player.user_id or player.id)
        item = player_stats[key]
        item["userId"] = str(player.user_id) if player.user_id else None
        item["nickname"] = (user.nickname if user and user.nickname else player.player_name)
        item["phone"] = user.phone if user else player.phone
        item["reservationCount"] = int(item["reservationCount"]) + 1
        if player.status == SessionPlayerStatus.CANCELLED:
            item["cancelledCount"] = int(item["cancelledCount"]) + 1
        if player.status != SessionPlayerStatus.CANCELLED and session.status == GameSessionStatus.COMPLETED:
            item["completedCount"] = int(item["completedCount"]) + 1

    active_players = sorted(
        player_stats.values(),
        key=lambda item: int(item["reservationCount"]),
        reverse=True,
    )[:8]
    risk_players = sorted(
        [item for item in player_stats.values() if int(item["cancelledCount"]) > 0],
        key=lambda item: (int(item["cancelledCount"]), int(item["reservationCount"])),
        reverse=True,
    )[:8]
    top_genres = [
        {"genre": genre, "count": count}
        for genre, count in genre_counter.most_common(8)
    ]
    ai_summary = (
        f"当前客户池 {int(total_players or 0)} 人，累计产生 {reservation_count} 次预约，"
        f"取消率 {round(_cancellation_rate(cancelled_count, reservation_count) * 100, 1)}%。"
        f"热门类型为 {('、'.join(item['genre'] for item in top_genres[:3]) if top_genres else '暂无明显趋势')}。"
    )

    return StorePlayerAnalyticsResponse(
        total_players=int(total_players or 0),
        reservation_count=reservation_count,
        completed_count=completed_count,
        cancelled_count=cancelled_count,
        active_reservation_count=active_count,
        cancellation_rate=_cancellation_rate(cancelled_count, reservation_count),
        estimated_revenue_cents=estimated_revenue,
        top_genres=top_genres,
        active_players=active_players,
        risk_players=risk_players,
        ai_summary=ai_summary,
    )
