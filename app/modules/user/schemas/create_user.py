"""创建普通用户请求结构。"""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,14}$")


class CreateUserRequest(BaseModel):
    """公开注册入口允许提交的安全字段。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phone: str = Field(max_length=20)
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        """移除常见分隔符，并验证国际化手机号格式。"""

        normalized = re.sub(r"[\s()-]", "", value)
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("手机号格式不正确")
        return normalized


class UpsertStorePlayerRequest(CreateUserRequest):
    """门店后台创建玩家，同时写入门店客户池信息。"""

    password: str = Field(min_length=8, max_length=128)
    preference: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class UpdateStorePlayerRequest(BaseModel):
    """门店后台维护玩家资料允许修改的字段。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phone: str | None = Field(default=None, max_length=20)
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)
    preference: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        """允许清空手机号；非空时走手机号格式校验。"""

        if value is None or not value.strip():
            return None
        normalized = re.sub(r"[\s()-]", "", value)
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("手机号格式不正确")
        return normalized
