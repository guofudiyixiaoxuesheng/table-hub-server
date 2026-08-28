"""阿里云 OSS V2 适配器。"""

import asyncio
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import alibabacloud_oss_v2 as oss  # type: ignore[import-untyped]

from app.core.config import settings


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    """前端直传 OSS 所需的临时授权信息。"""

    url: str
    headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    """OSS 对象校验所需的元数据。"""

    size: int
    etag: str
    content_type: str


class OssStorage:
    """封装预签名、对象校验和清单写入。"""

    def __init__(self) -> None:
        if not all(
            [
                settings.OSS_ACCESS_KEY_ID,
                settings.OSS_ACCESS_KEY_SECRET,
                settings.OSS_BUCKET,
            ]
        ):
            raise RuntimeError("OSS 配置不完整，请设置 AccessKey、Bucket 和 Endpoint")

        config = oss.config.load_default()
        config.region = settings.OSS_REGION
        config.endpoint = self._normalize_endpoint(settings.OSS_ENDPOINT)
        config.credentials_provider = oss.credentials.StaticCredentialsProvider(
            settings.OSS_ACCESS_KEY_ID,
            settings.OSS_ACCESS_KEY_SECRET,
        )
        self.client = oss.Client(config)
        self.bucket = settings.OSS_BUCKET

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        return (
            endpoint
            if endpoint.startswith(("http://", "https://"))
            else f"https://{endpoint}"
        )

    def presign_put(self, object_key: str, content_type: str) -> PresignedUpload:
        """生成短期有效、禁止覆盖的 V4 PUT URL。"""

        request = oss.PutObjectRequest(
            bucket=self.bucket,
            key=object_key,
            content_type=content_type,
            forbid_overwrite=True,
        )
        result = self.client.presign(
            request,
            expires=timedelta(seconds=settings.OSS_PRESIGN_EXPIRES_SECONDS),
        )
        if not result.url:
            raise RuntimeError("OSS 未返回预签名 URL")
        return PresignedUpload(
            url=result.url,
            headers={
                str(key): str(value)
                for key, value in (result.signed_headers or {}).items()
            },
        )

    async def head_object(self, object_key: str) -> ObjectMetadata:
        """读取对象元数据；SDK 同步请求放入工作线程。"""

        result = await asyncio.to_thread(
            self.client.head_object,
            oss.HeadObjectRequest(bucket=self.bucket, key=object_key),
        )
        return ObjectMetadata(
            size=int(result.content_length or 0),
            etag=str(result.etag or "").strip('"'),
            content_type=str(result.content_type or "application/octet-stream"),
        )

    async def put_json(self, object_key: str, payload: dict[str, Any]) -> None:
        """将版本清单写入 OSS。"""

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        await asyncio.to_thread(
            self.client.put_object,
            oss.PutObjectRequest(
                bucket=self.bucket,
                key=object_key,
                body=body,
                content_type="application/json; charset=utf-8",
            ),
        )
