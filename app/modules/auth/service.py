"""密码验证、JWT 签发和刷新令牌轮换。"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash  # type: ignore[import-untyped]
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.security import AuthenticationConfigurationError, AuthenticationError
from app.modules.auth.models import RefreshToken, Store, StoreInvite, StoreMember
from app.modules.auth.repository import (
    add_refresh_token,
    get_invite_for_update,
    get_login_identity,
    get_membership,
    get_refresh_token_for_update,
    get_user,
    revoke_user_refresh_tokens,
)
from app.modules.auth.schemas import (
    AuthUserResponse,
    DmInviteResponse,
    RegistrationType,
    TokenResponse,
)
from app.modules.user.models import User, UserRole, UserStatus

password_hash = PasswordHash.recommended()


@dataclass(frozen=True, slots=True)
class AuthResult:
    response: TokenResponse
    refresh_token: str


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    return bool(encoded and password_hash.verify(password, encoded))


def _encode_token(payload: dict[str, object]) -> str:
    if len(settings.JWT_SECRET_KEY.encode()) < 32:
        raise AuthenticationConfigurationError("JWT_SECRET_KEY 必须至少为 32 字节")
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _access_token(
    user: User, membership: StoreMember | None, now: datetime
) -> str:
    expires_at = now + timedelta(minutes=settings.JWT_ACCESS_EXPIRES_MINUTES)
    return _encode_token(
        {
            "sub": str(user.id),
            "store_id": str(membership.store_id) if membership else None,
            "role": membership.role if membership else user.role.value,
            "typ": "access",
            "iat": now,
            "exp": expires_at,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }
    )


async def _issue_tokens(
    user: User, membership: StoreMember | None, db: AsyncSession
) -> AuthResult:
    now = datetime.now(UTC)
    refresh_id = uuid.uuid4()
    refresh_expires_at = now + timedelta(days=settings.JWT_REFRESH_EXPIRES_DAYS)
    refresh_value = _encode_token(
        {
            "sub": str(user.id),
            "store_id": str(membership.store_id) if membership else None,
            "role": membership.role if membership else user.role.value,
            "jti": str(refresh_id),
            "typ": "refresh",
            "iat": now,
            "exp": refresh_expires_at,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }
    )
    await add_refresh_token(
        RefreshToken(
            id=refresh_id,
            user_id=user.id,
            store_id=membership.store_id if membership else None,
            expires_at=refresh_expires_at,
        ),
        db,
    )
    response = TokenResponse(
        accessToken=_access_token(user, membership, now),
        expiresIn=settings.JWT_ACCESS_EXPIRES_MINUTES * 60,
        user=AuthUserResponse(
            id=user.id,
            phone=user.phone or "",
            nickname=user.nickname,
            avatarUrl=user.avatar_url,
            storeId=membership.store_id if membership else None,
            storeName=membership.store.name if membership else None,
            role=membership.role if membership else user.role.value,
        ),
    )
    return AuthResult(response=response, refresh_token=refresh_value)


async def login(phone: str, password: str, db: AsyncSession) -> AuthResult:
    identity = await get_login_identity(phone, db)
    if identity is None or not verify_password(password, identity[0].password_hash):
        raise AuthenticationError("手机号或密码错误")
    user, membership = identity
    user.last_login_at = datetime.now(UTC)
    return await _issue_tokens(user, membership, db)


async def register(
    phone: str,
    password: str,
    nickname: str,
    registration_type: RegistrationType,
    store_name: str | None,
    invite_code: str | None,
    db: AsyncSession,
) -> AuthResult:
    if await get_login_identity(phone, db):
        raise ConflictError("该手机号已注册")
    role = {
        RegistrationType.USER: UserRole.USER,
        RegistrationType.STORE: UserRole.MANAGER,
        RegistrationType.DM: UserRole.DM,
    }[registration_type]
    invite = None
    if registration_type is RegistrationType.DM:
        invite = await get_invite_for_update(
            hashlib.sha256((invite_code or "").strip().upper().encode()).hexdigest(),
            db,
        )
        now = datetime.now(UTC)
        if (
            invite is None
            or invite.role != "dm"
            or invite.used_at is not None
            or invite.revoked_at is not None
            or invite.expires_at <= now
        ):
            raise ConflictError("DM 邀请码无效、已使用或已过期")

    user = User(
        phone=phone,
        password_hash=hash_password(password),
        nickname=nickname,
        role=role,
        status=UserStatus.ACTIVE,
        phone_verified_at=datetime.now(UTC),
    )
    store = Store(name=store_name or "") if registration_type is RegistrationType.STORE else None
    db.add(user)
    if store:
        db.add(store)
    try:
        await db.flush()
        membership = None
        if store:
            membership = StoreMember(
                user=user, store=store, role="manager", status="active"
            )
        elif invite:
            membership = StoreMember(
                user=user, store=invite.store, role="dm", status="active"
            )
            invite.used_at = datetime.now(UTC)
            invite.used_by_user_id = user.id
        if membership:
            db.add(membership)
            await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise ConflictError("该手机号已注册") from error
    return await _issue_tokens(user, membership, db)


async def create_dm_invite(
    user_id: uuid.UUID, store_id: uuid.UUID, db: AsyncSession
) -> DmInviteResponse:
    code = secrets.token_hex(4).upper()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    db.add(
        StoreInvite(
            store_id=store_id,
            created_by_user_id=user_id,
            code_hash=hashlib.sha256(code.encode()).hexdigest(),
            role="dm",
            expires_at=expires_at,
        )
    )
    await db.flush()
    return DmInviteResponse(code=code, expiresAt=expires_at)


async def change_password(
    user_id: uuid.UUID,
    store_id: uuid.UUID | None,
    current_password: str,
    new_password: str,
    db: AsyncSession,
) -> None:
    membership = await get_membership(user_id, store_id, db) if store_id else None
    user = membership.user if membership else await get_user(user_id, db)
    if user is None or not verify_password(current_password, user.password_hash):
        raise AuthenticationError("当前密码不正确")
    if current_password == new_password:
        raise ConflictError("新密码不能与当前密码相同")
    user.password_hash = hash_password(new_password)
    await revoke_user_refresh_tokens(user_id, datetime.now(UTC), db)


def _decode_refresh(token: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID | None]:
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={"require": ["exp", "sub", "jti", "typ"]},
        )
        if claims["typ"] != "refresh":
            raise AuthenticationError("刷新凭证类型错误")
        return (
            uuid.UUID(claims["jti"]),
            uuid.UUID(claims["sub"]),
            uuid.UUID(claims["store_id"]) if claims.get("store_id") else None,
        )
    except AuthenticationError:
        raise
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as error:
        raise AuthenticationError("刷新凭证无效或已过期") from error


async def refresh(refresh_value: str, db: AsyncSession) -> AuthResult:
    token_id, user_id, store_id = _decode_refresh(refresh_value)
    token = await get_refresh_token_for_update(token_id, db)
    now = datetime.now(UTC)
    if (
        token is None
        or token.user_id != user_id
        or token.store_id != store_id
        or token.revoked_at is not None
        or token.expires_at <= now
    ):
        raise AuthenticationError("刷新凭证已失效，请重新登录")
    membership = await get_membership(user_id, store_id, db) if store_id else None
    user = membership.user if membership else await get_user(user_id, db)
    if user is None or (store_id and membership is None):
        raise AuthenticationError("账户或门店成员关系已失效")

    token.revoked_at = now
    result = await _issue_tokens(user, membership, db)
    new_claims = jwt.decode(
        result.refresh_token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience=settings.JWT_AUDIENCE,
        issuer=settings.JWT_ISSUER,
    )
    token.replaced_by_id = uuid.UUID(new_claims["jti"])
    return result


async def logout(refresh_value: str | None, db: AsyncSession) -> None:
    if not refresh_value:
        return
    try:
        token_id, _, _ = _decode_refresh(refresh_value)
    except AuthenticationError:
        return
    token = await get_refresh_token_for_update(token_id, db)
    if token and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
