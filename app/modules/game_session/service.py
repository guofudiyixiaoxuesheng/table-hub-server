"""场次创建、容量和状态变更业务规则。"""

from __future__ import annotations

import random
import string
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApplicationError
from app.modules.game_session.models import GameSession, SessionPlayer, SessionPlayerStatus
from app.modules.game_session.models import GameSessionStatus
from app.modules.game_session.schemas import (
    CreateGameSessionRequest,
    DmOptionResponse,
    GameSessionDetailResponse,
    GameSessionResponse,
    ScriptOptionResponse,
    SessionPlayerRequest,
    SessionPlayerResponse,
    UpdateGameSessionRequest,
    UpdateSessionPlayerRequest,
)
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeResourceType,
)
from app.modules.user.models import StorePlayer, User, UserStatus


class GameSessionNotFoundError(ApplicationError):
    status_code = 404
    code = "game_session_not_found"


class SessionPlayerNotFoundError(ApplicationError):
    status_code = 404
    code = "session_player_not_found"


class GameSessionCapacityExceededError(ApplicationError):
    status_code = 409
    code = "game_session_capacity_exceeded"


def _reservation_code() -> str:
    return "".join(random.choices(string.digits, k=6))


async def _unique_reservation_code(db: AsyncSession) -> str:
    for _ in range(20):
        code = _reservation_code()
        exists = await db.scalar(select(SessionPlayer.id).where(SessionPlayer.reservation_code == code))
        if not exists:
            return code
    raise ApplicationError("预约码生成失败，请重试")


async def _joined_seats(session_id: uuid.UUID, db: AsyncSession) -> int:
    value = await db.scalar(
        select(func.coalesce(func.sum(SessionPlayer.seat_count), 0)).where(
            SessionPlayer.session_id == session_id,
            SessionPlayer.status != SessionPlayerStatus.CANCELLED,
        )
    )
    return int(value or 0)


async def _player_count(session_id: uuid.UUID, db: AsyncSession) -> int:
    value = await db.scalar(
        select(func.count()).select_from(SessionPlayer).where(
            SessionPlayer.session_id == session_id,
            SessionPlayer.status != SessionPlayerStatus.CANCELLED,
        )
    )
    return int(value or 0)


async def _to_session_response(session: GameSession, db: AsyncSession) -> GameSessionResponse:
    dm_name = None
    if session.dm_user_id:
        dm = await db.get(User, session.dm_user_id)
        dm_name = dm.nickname or dm.phone if dm else None
    return GameSessionResponse(
        id=session.id,
        storeId=session.store_id,
        scriptDocumentId=session.script_document_id,
        dmUserId=session.dm_user_id,
        title=session.title,
        scriptName=session.script_name,
        startTime=session.start_time,
        durationMinutes=session.duration_minutes,
        minPlayers=session.min_players,
        capacity=session.capacity,
        priceCents=session.price_cents,
        status=session.status,
        description=session.description,
        notes=session.notes,
        joinedSeats=await _joined_seats(session.id, db),
        playerCount=await _player_count(session.id, db),
        dmName=dm_name,
        createdAt=session.created_at,
        updatedAt=session.updated_at,
    )


async def _get_session(store_id: uuid.UUID, session_id: uuid.UUID, db: AsyncSession) -> GameSession:
    session = await db.get(GameSession, session_id)
    if session is None or session.store_id != store_id or session.deleted_at is not None:
        raise GameSessionNotFoundError("场次不存在")
    return session


async def list_script_options(store_id: uuid.UUID, keyword: str | None, db: AsyncSession) -> list[ScriptOptionResponse]:
    statement = (
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.resource_type == KnowledgeResourceType.SCRIPT,
            KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE,
            KnowledgeDocument.deleted_at.is_(None),
        )
        .order_by(KnowledgeDocument.updated_at.desc())
        .limit(50)
    )
    if keyword:
        statement = statement.where(KnowledgeDocument.name.ilike(f"%{keyword.strip()}%"))
    docs = (await db.scalars(statement)).all()
    return [
        ScriptOptionResponse(
            id=doc.id,
            name=doc.name,
            scriptGenre=doc.script_genre.value if doc.script_genre else None,
            description=doc.description,
        )
        for doc in docs
    ]


async def list_dm_options(store_id: uuid.UUID, db: AsyncSession) -> list[DmOptionResponse]:
    from app.modules.auth.models import StoreMember

    statement = (
        select(User)
        .join(StoreMember, StoreMember.user_id == User.id)
        .where(
            StoreMember.store_id == store_id,
            StoreMember.status == "active",
            StoreMember.role.in_(["dm", "manager", "admin"]),
            User.status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
        )
        .order_by(User.created_at.desc())
    )
    users = (await db.scalars(statement)).all()
    return [DmOptionResponse(id=user.id, nickname=user.nickname, phone=user.phone) for user in users]


async def list_game_sessions(
    store_id: uuid.UUID,
    keyword: str | None,
    db: AsyncSession,
    *,
    day: date | None = None,
    status: GameSessionStatus | None = None,
    script_document_id: uuid.UUID | None = None,
) -> list[GameSessionResponse]:
    statement = (
        select(GameSession)
        .where(GameSession.store_id == store_id, GameSession.deleted_at.is_(None))
        .order_by(GameSession.start_time.asc())
    )
    if day:
        start_at = datetime.combine(day, time.min).replace(tzinfo=UTC)
        end_at = start_at + timedelta(days=1)
        statement = statement.where(GameSession.start_time >= start_at, GameSession.start_time < end_at)
    if status:
        statement = statement.where(GameSession.status == status)
    if script_document_id:
        statement = statement.where(GameSession.script_document_id == script_document_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        statement = statement.where(or_(GameSession.title.ilike(like), GameSession.script_name.ilike(like)))
    sessions = (await db.scalars(statement)).all()
    return [await _to_session_response(session, db) for session in sessions]


async def create_game_session(store_id: uuid.UUID, payload: CreateGameSessionRequest, db: AsyncSession) -> GameSessionDetailResponse:
    script_name = payload.script_name
    if payload.script_document_id:
        doc = await db.get(KnowledgeDocument, payload.script_document_id)
        if doc and doc.store_id == store_id:
            script_name = doc.name
    session = GameSession(store_id=store_id, **payload.model_dump(by_alias=False, exclude={"script_name"}), script_name=script_name)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return await get_game_session_detail(store_id, session.id, db)


async def update_game_session(store_id: uuid.UUID, session_id: uuid.UUID, payload: UpdateGameSessionRequest, db: AsyncSession) -> GameSessionDetailResponse:
    session = await _get_session(store_id, session_id, db)
    values = payload.model_dump(by_alias=False)
    if payload.script_document_id:
        doc = await db.get(KnowledgeDocument, payload.script_document_id)
        if doc and doc.store_id == store_id:
            values["script_name"] = doc.name
    for key, value in values.items():
        setattr(session, key, value)
    await db.flush()
    await db.refresh(session)
    return await get_game_session_detail(store_id, session.id, db)


async def delete_game_session(store_id: uuid.UUID, session_id: uuid.UUID, db: AsyncSession) -> None:
    session = await _get_session(store_id, session_id, db)
    session.deleted_at = datetime.now(UTC)
    await db.flush()


async def get_game_session_detail(store_id: uuid.UUID, session_id: uuid.UUID, db: AsyncSession) -> GameSessionDetailResponse:
    session = await _get_session(store_id, session_id, db)
    base = await _to_session_response(session, db)
    players = (await db.scalars(select(SessionPlayer).where(SessionPlayer.session_id == session.id).order_by(SessionPlayer.created_at.asc()))).all()
    return GameSessionDetailResponse(**base.model_dump(by_alias=True), players=[SessionPlayerResponse.model_validate(item) for item in players])


async def add_session_player(store_id: uuid.UUID, session_id: uuid.UUID, payload: SessionPlayerRequest, db: AsyncSession) -> SessionPlayerResponse:
    session = await _get_session(store_id, session_id, db)
    if await _joined_seats(session.id, db) + payload.seat_count > session.capacity:
        raise GameSessionCapacityExceededError("当前场次人数已超过容量")
    if payload.user_id:
        user = await db.scalar(
            select(User)
            .join(StorePlayer, StorePlayer.user_id == User.id)
            .where(
                User.id == payload.user_id,
                StorePlayer.store_id == store_id,
                StorePlayer.deleted_at.is_(None),
            )
        )
        if user:
            payload.player_name = payload.player_name or user.nickname or user.phone or "未命名玩家"
            payload.phone = payload.phone or user.phone
        else:
            raise SessionPlayerNotFoundError("该玩家不在当前门店客户池中")
    player = SessionPlayer(session_id=session.id, reservation_code=await _unique_reservation_code(db), **payload.model_dump(by_alias=False))
    db.add(player)
    await db.flush()
    await db.refresh(player)
    return SessionPlayerResponse.model_validate(player)


async def update_session_player(store_id: uuid.UUID, session_id: uuid.UUID, player_id: uuid.UUID, payload: UpdateSessionPlayerRequest, db: AsyncSession) -> SessionPlayerResponse:
    session = await _get_session(store_id, session_id, db)
    player = await db.get(SessionPlayer, player_id)
    if player is None or player.session_id != session.id:
        raise SessionPlayerNotFoundError("约车玩家不存在")
    current = await _joined_seats(session.id, db)
    if player.status != SessionPlayerStatus.CANCELLED:
        current -= player.seat_count
    if payload.status != SessionPlayerStatus.CANCELLED and current + payload.seat_count > session.capacity:
        raise GameSessionCapacityExceededError("当前场次人数已超过容量")
    for key, value in payload.model_dump(by_alias=False).items():
        setattr(player, key, value)
    await db.flush()
    await db.refresh(player)
    return SessionPlayerResponse.model_validate(player)


async def delete_session_player(store_id: uuid.UUID, session_id: uuid.UUID, player_id: uuid.UUID, db: AsyncSession) -> None:
    session = await _get_session(store_id, session_id, db)
    player = await db.get(SessionPlayer, player_id)
    if player is None or player.session_id != session.id:
        raise SessionPlayerNotFoundError("约车玩家不存在")
    await db.delete(player)
    await db.flush()
