"""登录、刷新、退出和当前用户接口。"""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.responses import success_response
from app.core.config import settings
from app.core.database import get_database
from app.core.security import AuthenticationError, CurrentAccess, StoreManagerAccess
from app.modules.auth.repository import get_membership, get_user
from app.modules.auth.schemas import (
    AuthUserResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
)
from app.modules.auth.service import (
    change_password,
    create_dm_invite,
    login,
    logout,
    refresh,
    register,
)

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "table_hub_refresh"


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    return cast(Literal["lax", "strict", "none"], settings.AUTH_COOKIE_SAMESITE)


def _set_refresh_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=value,
        max_age=settings.JWT_REFRESH_EXPIRES_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=_cookie_samesite(),
        domain=settings.AUTH_COOKIE_DOMAIN,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=_cookie_samesite(),
        domain=settings.AUTH_COOKIE_DOMAIN,
        path="/api/v1/auth",
    )


@router.post("/login")
async def login_route(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    result = await login(payload.phone, payload.password, db)
    _set_refresh_cookie(response, result.refresh_token)
    return success_response(
        message="登录成功",
        data=result.response.model_dump(mode="json", by_alias=True),
    )


@router.post("/register", status_code=201)
async def register_route(
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    result = await register(
        payload.phone,
        payload.password,
        payload.nickname,
        payload.registration_type,
        payload.store_name,
        payload.invite_code,
        db,
    )
    _set_refresh_cookie(response, result.refresh_token)
    return success_response(
        message="账户创建成功",
        data=result.response.model_dump(mode="json", by_alias=True),
    )


@router.post("/refresh")
async def refresh_route(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    if not refresh_token:
        raise AuthenticationError("缺少刷新凭证，请重新登录")
    result = await refresh(refresh_token, db)
    _set_refresh_cookie(response, result.refresh_token)
    return success_response(data=result.response.model_dump(mode="json", by_alias=True))


@router.post("/logout")
async def logout_route(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    await logout(refresh_token, db)
    _clear_refresh_cookie(response)
    return success_response(message="已退出登录")


@router.post("/change-password")
async def change_password_route(
    payload: ChangePasswordRequest,
    response: Response,
    access: CurrentAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    await change_password(
        access.user_id,
        access.store_id,
        payload.current_password,
        payload.new_password,
        db,
    )
    _clear_refresh_cookie(response)
    return success_response(message="密码修改成功，请重新登录")


@router.post("/dm-invites", status_code=201)
async def create_dm_invite_route(
    access: StoreManagerAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    data = await create_dm_invite(access.user_id, access.store_id, db)
    return success_response(
        message="DM 邀请码创建成功",
        data=data.model_dump(mode="json", by_alias=True),
    )


@router.get("/me")
async def me_route(
    access: CurrentAccess,
    db: AsyncSession = Depends(get_database),  # noqa: B008
):
    membership = (
        await get_membership(access.user_id, access.store_id, db)
        if access.store_id
        else None
    )
    user = membership.user if membership else await get_user(access.user_id, db)
    if user is None:
        raise AuthenticationError("当前账户已失效")
    data = AuthUserResponse(
        id=user.id,
        phone=user.phone or "",
        nickname=user.nickname,
        avatarUrl=user.avatar_url,
        storeId=membership.store_id if membership else None,
        storeName=membership.store.name if membership else None,
        role=membership.role if membership else user.role.value,
    )
    return success_response(data=data.model_dump(mode="json", by_alias=True))
