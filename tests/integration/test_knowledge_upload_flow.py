"""剧本文件包上传的数据库集成流程。"""

import uuid
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_engine
from app.integrations.storage.oss import ObjectMetadata, PresignedUpload
from app.modules.knowledge.actions import (
    complete_upload_action,
    delete_document_action,
    get_loaded_markdown_action,
    get_manifest_action,
    initiate_upload_action,
    list_loaded_files_action,
    load_document_action,
)
from app.modules.knowledge.exceptions import KnowledgeDocumentNotFoundError
from app.modules.knowledge.repository import list_documents
from app.modules.knowledge.schemas import (
    CompleteKnowledgeDocumentUploadRequest,
    InitiateKnowledgeDocumentUploadRequest,
)


class FakeStorage:
    def __init__(self) -> None:
        self.sizes: dict[str, int] = {}
        self.manifests: dict[str, dict[str, object]] = {}
        self.objects: dict[str, bytes] = {}

    def presign_put(self, object_key: str, content_type: str) -> PresignedUpload:
        return PresignedUpload(
            url=f"https://oss.example.test/{object_key}",
            headers={"Content-Type": content_type},
        )

    async def head_object(self, object_key: str) -> ObjectMetadata:
        return ObjectMetadata(
            size=self.sizes[object_key],
            etag="verified-etag",
            content_type="text/plain",
        )

    async def put_json(
        self, object_key: str, payload: dict[str, object]
    ) -> None:
        self.manifests[object_key] = payload

    async def put_text(self, object_key: str, text: str) -> None:
        self.objects[object_key] = text.encode()

    async def get_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]

    async def get_text(self, object_key: str) -> str:
        return self.objects[object_key].decode()


@pytest.mark.asyncio
async def test_upload_folder_and_generate_exportable_manifest() -> None:
    store_id = uuid.uuid4()
    storage = FakeStorage()
    payload = InitiateKnowledgeDocumentUploadRequest.model_validate(
        {
            "resourceType": "script",
            "scriptGenre": "mystery_hardcore",
            "name": "测试剧本",
            "version": "v1",
            "description": "事务内测试，不写真实 OSS",
            "tags": ["推理"],
            "files": [
                {
                    "clientFileId": "csv-1",
                    "relativePath": "测试剧本/第一幕/角色.csv",
                    "size": 128,
                    "contentType": "text/csv",
                    "lastModified": 1,
                    "sha256": "a" * 64,
                },
                {
                    "clientFileId": "txt-1",
                    "relativePath": "测试剧本/assets/说明.txt",
                    "size": 64,
                    "contentType": "text/plain",
                    "lastModified": 2,
                    "sha256": "b" * 64,
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
                            {
                                "clientFileId": item.client_file_id,
                                "etag": "verified-etag",
                                "sha256": item.sha256,
                            }
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
            for target in initiated.files:
                storage.objects[target.object_key] = b"title,role\nAlice,detective\n"
            loaded = await load_document_action(
                initiated.document_id,
                initiated.version_id,
                store_id,
                session,
                storage,  # type: ignore[arg-type]
            )
            loaded_again = await list_loaded_files_action(
                initiated.document_id, initiated.version_id, store_id, session
            )
            markdown = await get_loaded_markdown_action(
                initiated.document_id,
                initiated.version_id,
                loaded.files[0].id,
                store_id,
                session,
                storage,  # type: ignore[arg-type]
            )
            documents = await list_documents(store_id, None, session)

            assert completed.status == "uploaded"
            assert manifest.status == "uploaded"
            assert len(manifest.files) == 2
            assert manifest.resource_type.value == "script"
            assert manifest.script_genre is not None
            assert manifest.script_genre.value == "mystery_hardcore"
            assert len(loaded.files) == 2
            assert loaded.files[0].status == "ready"
            assert len(loaded_again.files) == 2
            assert "Alice" in markdown.markdown
            assert len(documents) == 1
            assert documents[0][0].name == "测试剧本"
            saved_manifest = next(iter(storage.manifests.values()))
            saved_files = cast(list[dict[str, Any]], saved_manifest["files"])
            assert saved_manifest["name"] == "测试剧本"
            assert saved_manifest["scriptGenre"] == "mystery_hardcore"
            assert saved_files[0]["sha256"] == "a" * 64
            assert all(
                target.object_key.startswith(f"stores/{store_id}/knowledge/")
                for target in initiated.files
            )

            await delete_document_action(initiated.document_id, store_id, session)
            assert await list_documents(store_id, None, session) == []
            with pytest.raises(KnowledgeDocumentNotFoundError):
                await delete_document_action(initiated.document_id, store_id, session)
        finally:
            await session.close()
            await transaction.rollback()
