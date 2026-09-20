"""JWT 身份与门店权限验证。"""

import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)

from app.core.config import settings
from app.core.exceptions import ApplicationError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
optional_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticationError(ApplicationError):
    status_code = 401
    code = "authentication_required"


class PermissionDeniedError(ApplicationError):
    status_code = 403
    code = "permission_denied"


class AuthenticationConfigurationError(ApplicationError):
    status_code = 503
    code = "authentication_not_configured"


@dataclass(frozen=True, slots=True)
class StoreAccessContext:
    user_id: uuid.UUID
    store_id: uuid.UUID | None
    role: str


@dataclass(frozen=True, slots=True)
class StoreManagerContext:
    user_id: uuid.UUID
    store_id: uuid.UUID
    role: str


def require_authenticated_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> StoreAccessContext:
    """验证短期 Access Token 并返回可信门店身份。"""

    if len(settings.JWT_SECRET_KEY.encode()) < 32:
        raise AuthenticationConfigurationError("JWT_SECRET_KEY 必须至少为 32 字节")
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={"require": ["exp", "sub", "role", "typ"]},
        )
        if claims["typ"] != "access":
            raise AuthenticationError("登录凭证类型错误")
        context = StoreAccessContext(
            user_id=uuid.UUID(claims["sub"]),
            store_id=uuid.UUID(claims["store_id"]) if claims.get("store_id") else None,
            role=str(claims["role"]),
        )
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as error:
        raise AuthenticationError("登录凭证无效或已过期") from error
    # DM 可参与当前门店的日常操作，但不得删除资源。这里在后端统一
    # 拦截，避免仅隐藏前端按钮后仍可直接调用删除 API。
    if context.role == "dm" and request.method == "DELETE":
        raise PermissionDeniedError("DM 账号不允许删除资源")
    return context


def get_optional_access(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer_scheme)],
) -> StoreAccessContext | None:
    """可选登录身份。

    用在“游客可浏览、登录后字段更多”的接口上。没有 token 或 token 失效时返回 None，
    不打断公开读取流程。
    """

    if credentials is None:
        return None
    try:
        return require_authenticated_user(request, credentials.credentials)
    except AuthenticationError:
        return None


def require_store_manager(
    context: Annotated[StoreAccessContext, Depends(require_authenticated_user)],
) -> StoreManagerContext:
    """仅允许平台管理员或门店店长执行写操作。"""

    if context.role not in {"admin", "manager", "dm"} or context.store_id is None:
        raise PermissionDeniedError("仅管理员、店长或 DM 可以执行此操作")
    return StoreManagerContext(
        user_id=context.user_id,
        store_id=context.store_id,
        role=context.role,
    )


CurrentAccess = Annotated[StoreAccessContext, Depends(require_authenticated_user)]
StoreManagerAccess = Annotated[StoreManagerContext, Depends(require_store_manager)]
