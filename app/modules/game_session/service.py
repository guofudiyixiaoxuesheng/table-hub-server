"""场次创建、容量和状态变更业务规则。"""

from __future__ import annotations

import random
import string
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ApplicationError, ConflictError
from app.modules.game_session.models import GameSession, Room, SessionJoinSource, SessionPlayer, SessionPlayerStatus
from app.modules.game_session.models import GameSessionStatus
from app.modules.game_session.schemas import (
    CreateGameSessionRequest,
    DmOptionResponse,
    GameSessionDetailResponse,
    GameSessionResponse,
    CreateRoomRequest,
    RoomResponse,
    SessionImageAssetResponse,
    ScriptOptionResponse,
    SessionPlayerRequest,
    SessionPlayerResponse,
    UpdateRoomRequest,
    UpdateGameSessionRequest,
    UpdateSessionPlayerRequest,
)
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeParsedAsset,
    KnowledgeParsedAssetType,
    KnowledgeVersion,
    KnowledgeResourceType,
)
from app.integrations.storage.oss import OssStorage
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


class RoomNotFoundError(ApplicationError):
    status_code = 404
    code = "room_not_found"


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


async def _my_reservation(
    session_id: uuid.UUID,
    user_id: uuid.UUID | None,
    db: AsyncSession,
) -> SessionPlayer | None:
    if user_id is None:
        return None
    return await db.scalar(
        select(SessionPlayer)
        .where(
            SessionPlayer.session_id == session_id,
            SessionPlayer.user_id == user_id,
        )
        .order_by(SessionPlayer.created_at.desc())
        .limit(1)
    )


async def _asset_preview_url(
    asset_id: uuid.UUID | str | None,
    store_id: uuid.UUID,
    db: AsyncSession,
) -> str | None:
    """按门店校验知识库图片归属后，再生成短期可访问预览地址。"""

    if not asset_id:
        return None
    try:
        resolved_id = uuid.UUID(str(asset_id))
    except ValueError:
        return None
    asset = await db.scalar(
        select(KnowledgeParsedAsset)
        .join(KnowledgeVersion, KnowledgeParsedAsset.version_id == KnowledgeVersion.id)
        .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeParsedAsset.id == resolved_id,
            KnowledgeDocument.store_id == store_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
    )
    if asset is None:
        return None
    return OssStorage().presign_get(asset.asset_key)


async def _resolve_session_images(session: GameSession, db: AsyncSession) -> tuple[str | None, list[str]]:
    if session.cover_image_source == "knowledge_asset":
        cover_url = await _asset_preview_url(session.cover_image_asset_id, session.store_id, db)
    else:
        cover_url = session.cover_image_url

    if session.detail_image_source == "knowledge_asset":
        detail_urls = [
            url
            for url in [
                await _asset_preview_url(asset_id, session.store_id, db)
                for asset_id in (session.detail_image_asset_ids or [])
            ]
            if url
        ]
    else:
        detail_urls = session.detail_image_urls or []
    return cover_url, detail_urls


async def _to_session_response(session: GameSession, db: AsyncSession, current_user_id: uuid.UUID | None = None) -> GameSessionResponse:
    dm_name = None
    if session.dm_user_id:
        dm = await db.get(User, session.dm_user_id)
        dm_name = dm.nickname or dm.phone if dm else None
    cover_url, detail_urls = await _resolve_session_images(session, db)
    my_reservation = await _my_reservation(session.id, current_user_id, db)
    return GameSessionResponse(
        id=session.id,
        storeId=session.store_id,
        scriptDocumentId=session.script_document_id,
        dmUserId=session.dm_user_id,
        roomId=session.room_id,
        roomName=session.room.name if session.room else None,
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
        coverImageSource=session.cover_image_source,
        coverImageAssetId=session.cover_image_asset_id,
        coverImageUrl=cover_url,
        detailImageSource=session.detail_image_source,
        detailImageAssetIds=[uuid.UUID(str(item)) for item in (session.detail_image_asset_ids or [])],
        detailImageUrls=detail_urls,
        joinedSeats=await _joined_seats(session.id, db),
        playerCount=await _player_count(session.id, db),
        dmName=dm_name,
        myReservationId=my_reservation.id if my_reservation else None,
        myReservationStatus=my_reservation.status if my_reservation else None,
        myReservationCode=my_reservation.reservation_code if my_reservation else None,
        createdAt=session.created_at,
        updatedAt=session.updated_at,
    )


async def _get_session(store_id: uuid.UUID, session_id: uuid.UUID, db: AsyncSession) -> GameSession:
    session = await db.scalar(
        select(GameSession)
        .options(selectinload(GameSession.room))
        .where(GameSession.id == session_id)
    )
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
            scriptGenre=doc.script_genre,
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


async def _get_room(store_id: uuid.UUID, room_id: uuid.UUID, db: AsyncSession) -> Room:
    room = await db.get(Room, room_id)
    if room is None or room.store_id != store_id or room.deleted_at is not None:
        raise RoomNotFoundError("房间不存在")
    return room


async def _validate_room(store_id: uuid.UUID, room_id: uuid.UUID | None, db: AsyncSession) -> None:
    if room_id:
        await _get_room(store_id, room_id, db)


async def list_rooms(store_id: uuid.UUID, db: AsyncSession, include_disabled: bool = False) -> list[RoomResponse]:
    filters = [Room.store_id == store_id, Room.deleted_at.is_(None)]
    if not include_disabled:
        filters.append(Room.status == "active")
    rows = (
        await db.scalars(
            select(Room)
            .where(*filters)
            .order_by(Room.status.asc(), Room.created_at.asc())
        )
    ).all()
    return [RoomResponse.model_validate(item) for item in rows]


async def create_room(store_id: uuid.UUID, payload: CreateRoomRequest, db: AsyncSession) -> RoomResponse:
    room = Room(store_id=store_id, **payload.model_dump())
    db.add(room)
    await db.flush()
    await db.refresh(room)
    return RoomResponse.model_validate(room)


async def update_room(store_id: uuid.UUID, room_id: uuid.UUID, payload: UpdateRoomRequest, db: AsyncSession) -> RoomResponse:
    room = await _get_room(store_id, room_id, db)
    for key, value in payload.model_dump().items():
        setattr(room, key, value)
    await db.flush()
    await db.refresh(room)
    return RoomResponse.model_validate(room)


async def delete_room(store_id: uuid.UUID, room_id: uuid.UUID, db: AsyncSession) -> None:
    room = await _get_room(store_id, room_id, db)
    room.deleted_at = datetime.now(UTC)
    await db.flush()


async def list_script_image_assets(
    store_id: uuid.UUID,
    script_document_id: uuid.UUID,
    db: AsyncSession,
    storage: OssStorage | None = None,
) -> list[SessionImageAssetResponse]:
    """列出某个剧本知识库资源解析出来的图片，供场次主图/详情图复用。"""

    document = await db.get(KnowledgeDocument, script_document_id)
    if document is None or document.store_id != store_id or document.deleted_at is not None:
        return []
    if document.resource_type != KnowledgeResourceType.SCRIPT or document.active_version_id is None:
        return []

    statement = (
        select(KnowledgeParsedAsset)
        .options(selectinload(KnowledgeParsedAsset.source_file))
        .join(KnowledgeVersion, KnowledgeParsedAsset.version_id == KnowledgeVersion.id)
        .where(
            KnowledgeVersion.document_id == document.id,
            KnowledgeParsedAsset.version_id == document.active_version_id,
            KnowledgeParsedAsset.asset_type == KnowledgeParsedAssetType.IMAGE,
        )
        .order_by(KnowledgeParsedAsset.page_number.asc().nullslast(), KnowledgeParsedAsset.created_at.asc())
        .limit(100)
    )
    assets = (await db.scalars(statement)).all()
    oss = storage or OssStorage()
    return [
        SessionImageAssetResponse(
            id=asset.id,
            label=asset.caption
            or str((asset.extra_metadata or {}).get("filename") or asset.original_ref or asset.source_file.relative_path),
            previewUrl=oss.presign_get(asset.asset_key),
            relativePath=asset.source_file.relative_path if asset.source_file else None,
            pageNumber=asset.page_number,
        )
        for asset in assets
    ]


async def list_game_sessions(
    store_id: uuid.UUID,
    keyword: str | None,
    db: AsyncSession,
    *,
    day: date | None = None,
    status: GameSessionStatus | None = None,
    script_document_id: uuid.UUID | None = None,
    room_id: uuid.UUID | None = None,
) -> list[GameSessionResponse]:
    statement = (
        select(GameSession)
        .options(selectinload(GameSession.room))
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
    if room_id:
        statement = statement.where(GameSession.room_id == room_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        statement = statement.where(or_(GameSession.title.ilike(like), GameSession.script_name.ilike(like)))
    sessions = (await db.scalars(statement)).all()
    return [await _to_session_response(session, db) for session in sessions]


async def create_game_session(store_id: uuid.UUID, payload: CreateGameSessionRequest, db: AsyncSession) -> GameSessionDetailResponse:
    await _validate_room(store_id, payload.room_id, db)
    script_name = payload.script_name
    if payload.script_document_id:
        doc = await db.get(KnowledgeDocument, payload.script_document_id)
        if doc and doc.store_id == store_id:
            script_name = doc.name
    values = payload.model_dump(by_alias=False, exclude={"script_name"})
    values["detail_image_asset_ids"] = [str(item) for item in values.get("detail_image_asset_ids", [])]
    session = GameSession(store_id=store_id, **values, script_name=script_name)
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return await get_game_session_detail(store_id, session.id, db)


async def update_game_session(store_id: uuid.UUID, session_id: uuid.UUID, payload: UpdateGameSessionRequest, db: AsyncSession) -> GameSessionDetailResponse:
    session = await _get_session(store_id, session_id, db)
    await _validate_room(store_id, payload.room_id, db)
    values = payload.model_dump(by_alias=False)
    values["detail_image_asset_ids"] = [str(item) for item in values.get("detail_image_asset_ids", [])]
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


async def cancel_game_session(store_id: uuid.UUID, session_id: uuid.UUID, db: AsyncSession) -> GameSessionDetailResponse:
    """取消场次：保留场次和报名记录，只把场次状态改为已取消。"""

    session = await _get_session(store_id, session_id, db)
    session.status = GameSessionStatus.CANCELLED
    await db.flush()
    await db.refresh(session)
    return await get_game_session_detail(store_id, session.id, db)


async def get_game_session_detail(
    store_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession,
    current_user_id: uuid.UUID | None = None,
) -> GameSessionDetailResponse:
    session = await _get_session(store_id, session_id, db)
    base = await _to_session_response(session, db, current_user_id=current_user_id)
    players = (await db.scalars(select(SessionPlayer).where(SessionPlayer.session_id == session.id).order_by(SessionPlayer.created_at.asc()))).all()
    return GameSessionDetailResponse(**base.model_dump(by_alias=True), players=[SessionPlayerResponse.model_validate(item) for item in players])


async def join_game_session(
    store_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> GameSessionDetailResponse:
    session = await _get_session(store_id, session_id, db)
    if session.status != GameSessionStatus.RECRUITING:
        raise ConflictError("当前场次暂不可预约")
    existing = await _my_reservation(session.id, user_id, db)
    if existing and existing.status != SessionPlayerStatus.CANCELLED:
        return await get_game_session_detail(store_id, session.id, db, current_user_id=user_id)
    if await _joined_seats(session.id, db) + 1 > session.capacity:
        raise GameSessionCapacityExceededError("当前场次人数已满")

    user = await db.get(User, user_id)
    player_name = user.nickname or user.phone if user else "未命名玩家"
    phone = user.phone if user else None
    if existing and existing.status == SessionPlayerStatus.CANCELLED:
        existing.status = SessionPlayerStatus.CONFIRMED
        existing.seat_count = 1
        existing.source = SessionJoinSource.H5
        existing.player_name = player_name
        existing.phone = phone
        existing.updated_at = datetime.now(UTC)
    else:
        db.add(
            SessionPlayer(
                session_id=session.id,
                user_id=user_id,
                player_name=player_name,
                phone=phone,
                seat_count=1,
                source=SessionJoinSource.H5,
                status=SessionPlayerStatus.CONFIRMED,
                reservation_code=await _unique_reservation_code(db),
            )
        )
    await db.flush()
    return await get_game_session_detail(store_id, session.id, db, current_user_id=user_id)


async def cancel_my_session_join(
    store_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> GameSessionDetailResponse:
    session = await _get_session(store_id, session_id, db)
    reservation = await _my_reservation(session.id, user_id, db)
    if reservation is None or reservation.status == SessionPlayerStatus.CANCELLED:
        raise SessionPlayerNotFoundError("当前没有可取消的约车记录")
    reservation.status = SessionPlayerStatus.CANCELLED
    reservation.updated_at = datetime.now(UTC)
    await db.flush()
    return await get_game_session_detail(store_id, session.id, db, current_user_id=user_id)


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
