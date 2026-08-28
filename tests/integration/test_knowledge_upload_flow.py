"""剧本文件包上传的数据库集成流程。"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_engine
from app.integrations.storage.oss import ObjectMetadata, PresignedUpload
from app.modules.knowledge.actions import (
    complete_upload_action,
    get_manifest_action,
    initiate_upload_action,
)
from app.modules.knowledge.repository import list_documents
from app.modules.knowledge.schemas import (
    CompleteKnowledgeDocumentUploadRequest,
    InitiateKnowledgeDocumentUploadRequest,
)


class FakeStorage:
    def __init__(self) -> None:
        self.sizes: dict[str, int] = {}
        self.manifests: dict[str, dict[str, object]] = {}

    def presign_put(self, object_key: str, content_type: str) -> PresignedUpload:
        return PresignedUpload(
            url=f"https://oss.example.test/{object_key}",
            headers={"Content-Type": content_type},
        )

    async def head_object(self, object_key: str) -> ObjectMetadata:
        return ObjectMetadata(
            size=self.sizes[object_key],
            etag="verified-etag",
            content_type="application/pdf",
        )

    async def put_json(
        self, object_key: str, payload: dict[str, object]
    ) -> None:
        self.manifests[object_key] = payload


@pytest.mark.asyncio
async def test_upload_folder_and_generate_exportable_manifest() -> None:
    store_id = uuid.uuid4()
    storage = FakeStorage()
    payload = InitiateKnowledgeDocumentUploadRequest.model_validate(
        {
            "resourceType": "script",
            "name": "测试剧本",
            "version": "v1",
            "description": "事务内测试，不写真实 OSS",
            "tags": ["推理"],
            "files": [
                {
                    "clientFileId": "pdf-1",
                    "relativePath": "测试剧本/正文.pdf",
                    "size": 128,
                    "contentType": "application/pdf",
                    "lastModified": 1,
                },
                {
                    "clientFileId": "cover-1",
                    "relativePath": "测试剧本/images/cover.jpg",
                    "size": 64,
                    "contentType": "image/jpeg",
                    "lastModified": 2,
                },
            ],
        }
    )

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            initiated = await initiate_upload_action(
                payload, store_id, session, storage  # type: ignore[arg-type]
            )
            storage.sizes = {
                target.object_key: file.size
                for target, file in zip(initiated.files, payload.files, strict=True)
            }
            completed = await complete_upload_action(
                initiated.upload_id,
                CompleteKnowledgeDocumentUploadRequest.model_validate(
                    {
                        "files": [
                            {"clientFileId": item.client_file_id, "etag": "verified-etag"}
                            for item in payload.files
                        ]
                    }
                ),
                store_id,
                session,
                storage,  # type: ignore[arg-type]
            )
            manifest = await get_manifest_action(
                initiated.document_id, initiated.version_id, store_id, session
            )
            documents = await list_documents(store_id, None, session)

            assert completed.status == "uploaded"
            assert manifest.status == "uploaded"
            assert len(manifest.files) == 2
            assert manifest.resource_type.value == "script"
            assert len(documents) == 1
            assert documents[0][0].name == "测试剧本"
            assert next(iter(storage.manifests.values()))["name"] == "测试剧本"
            assert all(
                target.object_key.startswith(f"stores/{store_id}/knowledge/")
                for target in initiated.files
            )
        finally:
            await session.close()
            await transaction.rollback()
