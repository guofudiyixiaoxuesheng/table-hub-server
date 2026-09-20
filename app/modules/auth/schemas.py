"""认证请求与安全响应结构。"""

import re
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,14}$")


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phone: str = Field(max_length=20)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        normalized = re.sub(r"[\s()-]", "", value)
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("手机号格式不正确")
        return normalized


class SmsCodeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    phone: str = Field(max_length=20)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        normalized = re.sub(r"[\s()-]", "", value)
        if not PHONE_PATTERN.fullmatch(normalized):
            raise ValueError("手机号格式不正确")
        return normalized


class SmsLoginRequest(SmsCodeRequest):
    code: str = Field(min_length=4, max_length=8)
    nickname: str | None = Field(default=None, max_length=50)


class RegistrationType(str, Enum):
    USER = "user"
    STORE = "store"
    DM = "dm"


class RegisterRequest(LoginRequest):
    registration_type: RegistrationType = Field(alias="registrationType")
    nickname: str = Field(min_length=1, max_length=50)
    store_name: str | None = Field(default=None, alias="storeName", max_length=120)
    invite_code: str | None = Field(default=None, alias="inviteCode", max_length=32)

    @model_validator(mode="after")
    def validate_registration_fields(self):
        if self.registration_type is RegistrationType.STORE and not self.store_name:
            raise ValueError("门店注册必须填写门店名称")
        if self.registration_type is RegistrationType.DM and not self.invite_code:
            raise ValueError("DM 注册必须填写门店邀请码")
        return self


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str | None = Field(default=None, alias="currentPassword", min_length=8, max_length=128)
    new_password: str = Field(alias="newPassword", min_length=8, max_length=128)


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    phone: str
    nickname: str | None
    avatar_url: str | None = Field(alias="avatarUrl")
    store_id: uuid.UUID | None = Field(alias="storeId")
    store_name: str | None = Field(alias="storeName")
    role: str
    has_password: bool = Field(alias="hasPassword")


class TokenResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field(alias="accessToken")
    token_type: str = Field(alias="tokenType", default="Bearer")
    expires_in: int = Field(alias="expiresIn")
    user: AuthUserResponse


class RefreshClaims(BaseModel):
    sub: uuid.UUID
    store_id: uuid.UUID | None
    role: str
    jti: uuid.UUID
    exp: datetime


class DmInviteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    expires_at: datetime = Field(alias="expiresAt")


class StoreMemberResponse(BaseModel):
    """门店员工/DM 的安全展示字段。"""

    model_config = ConfigDict(populate_by_name=True)

    id: uuid.UUID
    user_id: uuid.UUID = Field(alias="userId")
    nickname: str | None
    phone: str
    role: str
    status: str
    created_at: datetime = Field(alias="createdAt")


class AssignDmRequest(SmsCodeRequest):
    """将已注册账户关联到当前门店并授予 DM 角色。"""


class PublicDemoLoginRequest(BaseModel):
    """公开演示入口提交的邀请码。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(min_length=16, max_length=128)
