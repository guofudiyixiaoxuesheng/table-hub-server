import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    AuthenticationError,
    PermissionDeniedError,
    require_authenticated_user,
    require_store_manager,
)


def create_token(role: str) -> tuple[str, uuid.UUID]:
    store_id = uuid.uuid4()
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "store_id": str(store_id),
            "role": role,
            "typ": "access",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, store_id


TEST_SECRET = "unit-test-secret-with-at-least-32-bytes"


def test_manager_token_provides_trusted_store_id(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", TEST_SECRET)
    token, store_id = create_token("manager")

    context = require_store_manager(require_authenticated_user(token))

    assert context.store_id == store_id
    assert context.role == "manager"


def test_regular_user_cannot_mint_oss_upload(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", TEST_SECRET)
    token, _ = create_token("user")

    with pytest.raises(PermissionDeniedError):
        require_store_manager(require_authenticated_user(token))


def test_regular_user_token_can_have_no_store(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", TEST_SECRET)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "store_id": None,
            "role": "user",
            "typ": "access",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    context = require_authenticated_user(token)

    assert context.store_id is None
    assert context.role == "user"


def test_invalid_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", TEST_SECRET)

    with pytest.raises(AuthenticationError):
        require_authenticated_user("not-a-jwt")
