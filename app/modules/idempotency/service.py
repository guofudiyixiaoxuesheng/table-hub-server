"""幂等请求校验与结果复用。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import StoreAccessContext
from app.modules.idempotency.models import IdempotencyRecord

HEADER_NAME = "Idempotency-Key"


@dataclass
class IdempotencyGuard:
    record: IdempotencyRecord | None
    replay_response: dict[str, Any] | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_response is not None


def _canonical_body_hash(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8")) if body else None
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        source = canonical.encode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError):
        source = body
    return hashlib.sha256(source).hexdigest()


def _owner(access: StoreAccessContext | None, guest_id: str | None = None) -> tuple[str | None, str | None]:
    if access:
        return "user", str(access.user_id)
    if guest_id:
        return "guest", guest_id
    return None, None


async def begin_idempotency(
    *,
    request: Request,
    db: AsyncSession,
    access: StoreAccessContext | None = None,
    guest_id: str | None = None,
    scope: str | None = None,
) -> IdempotencyGuard:
    """开始幂等保护；未提供 header 时直接放行。"""

    key = request.headers.get(HEADER_NAME)
    if not key:
        return IdempotencyGuard(record=None)

    key = key.strip()
    if not key:
        return IdempotencyGuard(record=None)
    if len(key) > 120:
        raise ConflictError("本次提交标识过长，请重新提交")

    request_hash = _canonical_body_hash(await request.body())
    record_scope = scope or f"{request.method}:{request.url.path}"
    owner_type, owner_id = _owner(access, guest_id)
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == record_scope,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    if existing:
        if existing.owner_type != owner_type or existing.owner_id != owner_id:
            raise ConflictError("本次提交标识已被其他用户使用，请重新提交")
        if existing.request_hash != request_hash:
            raise ConflictError("本次提交标识已被其他操作使用，请重新提交")
        if existing.status == "completed" and existing.response_body is not None:
            return IdempotencyGuard(record=existing, replay_response=existing.response_body)
        raise ConflictError("相同请求正在处理中，请稍后重试")

    record = IdempotencyRecord(
        scope=record_scope,
        idempotency_key=key,
        request_hash=request_hash,
        owner_type=owner_type,
        owner_id=owner_id,
    )
    db.add(record)
    await db.flush()
    return IdempotencyGuard(record=record)


async def complete_idempotency(
    *,
    guard: IdempotencyGuard,
    response_body: dict[str, Any],
    db: AsyncSession,
) -> None:
    """保存首次成功响应，供后续同 key 重试直接复用。"""

    if guard.record is None:
        return
    guard.record.status = "completed"
    guard.record.response_body = response_body
    await db.flush()
