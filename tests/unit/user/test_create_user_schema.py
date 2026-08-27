"""创建用户请求结构测试。"""

import pytest
from pydantic import ValidationError

from app.modules.user.schemas import CreateUserRequest


def test_create_user_normalizes_phone() -> None:
    request = CreateUserRequest(phone="138 0013 8000")

    assert request.phone == "13800138000"


def test_create_user_rejects_invalid_phone() -> None:
    with pytest.raises(ValidationError):
        CreateUserRequest(phone="123")


def test_create_user_rejects_role_escalation() -> None:
    with pytest.raises(ValidationError):
        CreateUserRequest(phone="13800138000", role="admin")
