"""登录、刷新轮换和退出的数据库集成测试。"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_engine
from app.core.exceptions import ConflictError
from app.core.security import AuthenticationError
from app.modules.auth.models import Store, StoreMember
from app.modules.auth.schemas import RegistrationType
from app.modules.auth.service import (
    assign_existing_user_as_dm,
    change_password,
    create_dm_invite,
    hash_password,
    list_store_members,
    login,
    login_with_public_demo_code,
    logout,
    refresh,
    register,
)
from app.modules.user.models import User, UserRole, UserStatus


@pytest.mark.asyncio
async def test_login_refresh_rotation_and_logout(monkeypatch) -> None:
    monkeypatch.setattr(
        settings, "JWT_SECRET_KEY", "integration-test-secret-with-at-least-32-bytes"
    )
    await async_engine.dispose(close=False)
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        db = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            user = User(
                phone=f"138{uuid.uuid4().int % 100_000_000:08d}",
                password_hash=hash_password("safe-password-123"),
                nickname="测试店长",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            store = Store(name="事务测试门店")
            db.add_all([user, store])
            await db.flush()
            db.add(
                StoreMember(
                    user_id=user.id,
                    store_id=store.id,
                    role="admin",
                    status="active",
                )
            )
            await db.flush()

            logged_in = await login(user.phone or "", "safe-password-123", db)
            assert logged_in.response.user.store_id == store.id
            assert logged_in.response.user.role == "admin"

            rotated = await refresh(logged_in.refresh_token, db)
            assert rotated.refresh_token != logged_in.refresh_token
            with pytest.raises(AuthenticationError):
                await refresh(logged_in.refresh_token, db)

            await logout(rotated.refresh_token, db)
            with pytest.raises(AuthenticationError):
                await refresh(rotated.refresh_token, db)
        finally:
            await db.close()
            await transaction.rollback()


@pytest.mark.asyncio
async def test_register_and_change_password(monkeypatch) -> None:
    monkeypatch.setattr(
        settings, "JWT_SECRET_KEY", "integration-test-secret-with-at-least-32-bytes"
    )
    await async_engine.dispose(close=False)
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        db = AsyncSession(bind=connection, expire_on_commit=False)
        phone = f"139{uuid.uuid4().int % 100_000_000:08d}"
        try:
            registered = await register(
                phone,
                "initial-password-123",
                "新店长",
                RegistrationType.STORE,
                "新注册门店",
                None,
                db,
            )
            assert registered.response.user.role == "manager"
            assert registered.response.user.store_name == "新注册门店"
            with pytest.raises(ConflictError):
                await register(
                    phone,
                    "another-password",
                    "重复",
                    RegistrationType.STORE,
                    "重复门店",
                    None,
                    db,
                )

            await change_password(
                registered.response.user.id,
                registered.response.user.store_id,
                "initial-password-123",
                "changed-password-456",
                db,
            )
            with pytest.raises(AuthenticationError):
                await refresh(registered.refresh_token, db)
            with pytest.raises(AuthenticationError):
                await login(phone, "initial-password-123", db)
            logged_in = await login(phone, "changed-password-456", db)
            assert logged_in.response.user.id == registered.response.user.id
        finally:
            await db.close()
            await transaction.rollback()


@pytest.mark.asyncio
async def test_user_and_invited_dm_registration(monkeypatch) -> None:
    monkeypatch.setattr(
        settings, "JWT_SECRET_KEY", "integration-test-secret-with-at-least-32-bytes"
    )
    await async_engine.dispose(close=False)
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        db = AsyncSession(bind=connection, expire_on_commit=False)
        suffix = uuid.uuid4().int % 10_000_000
        try:
            player = await register(
                f"136{suffix:08d}",
                "player-password-123",
                "普通玩家",
                RegistrationType.USER,
                None,
                None,
                db,
            )
            assert player.response.user.role == "user"
            assert player.response.user.store_id is None
            refreshed_player = await refresh(player.refresh_token, db)
            assert refreshed_player.response.user.store_id is None

            manager = await register(
                f"137{suffix:08d}",
                "manager-password-123",
                "邀请店长",
                RegistrationType.STORE,
                "邀请测试门店",
                None,
                db,
            )
            assert manager.response.user.store_id is not None
            invite = await create_dm_invite(
                manager.response.user.id,
                manager.response.user.store_id,
                db,
            )
            dm = await register(
                f"135{suffix:08d}",
                "dm-password-123",
                "测试 DM",
                RegistrationType.DM,
                None,
                invite.code,
                db,
            )
            assert dm.response.user.role == "dm"
            assert dm.response.user.store_id == manager.response.user.store_id
            monkeypatch.setattr(settings, "PUBLIC_DEMO_INVITE_CODE", "demo-invite-code-123456")
            monkeypatch.setattr(settings, "PUBLIC_DEMO_ACCOUNT_PHONE", dm.response.user.phone)
            demo_session = await login_with_public_demo_code("demo-invite-code-123456", db)
            assert demo_session.response.user.id == dm.response.user.id
            assert demo_session.response.user.role == "dm"
            members = await list_store_members(manager.response.user.store_id, db)
            assert [(member.nickname, member.role) for member in members] == [
                ("邀请店长", "manager"),
                ("测试 DM", "dm"),
            ]
            with pytest.raises(ConflictError):
                await register(
                    f"134{suffix:08d}",
                    "second-dm-password",
                    "重复使用者",
                    RegistrationType.DM,
                    None,
                    invite.code,
                    db,
                )

            promoted = await assign_existing_user_as_dm(
                player.response.user.phone,
                manager.response.user.store_id,
                db,
            )
            assert promoted.nickname == "普通玩家"
            assert promoted.role == "dm"
            promoted_login = await login(
                player.response.user.phone, "player-password-123", db
            )
            assert (
                promoted_login.response.user.store_id == manager.response.user.store_id
            )
            assert promoted_login.response.user.role == "dm"
        finally:
            await db.close()
            await transaction.rollback()
