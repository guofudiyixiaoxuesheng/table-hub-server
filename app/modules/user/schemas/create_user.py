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
