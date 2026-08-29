import pytest
from pydantic import ValidationError

from app.modules.knowledge.schemas import InitiateKnowledgeDocumentUploadRequest


def make_payload(**overrides):
    payload = {
        "resourceType": "script",
        "scriptGenre": "mystery_hardcore",
        "name": "雾隐长夜",
        "version": "v1",
        "tags": ["情感", "情感", " 6人 "],
        "files": [
            {
                "clientFileId": "0-12-1",
                "relativePath": "雾隐长夜/正文.pdf",
                "size": 12,
                "contentType": "application/pdf",
                "lastModified": 1,
                "sha256": "a" * 64,
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_upload_schema_accepts_frontend_camel_case() -> None:
    payload = InitiateKnowledgeDocumentUploadRequest.model_validate(make_payload())

    assert payload.name == "雾隐长夜"
    assert payload.script_genre is not None
    assert payload.script_genre.value == "mystery_hardcore"
    assert payload.tags == ["情感", "6人"]
    assert payload.files[0].relative_path.endswith("正文.pdf")


def test_upload_schema_only_accepts_script_resource() -> None:
    with pytest.raises(ValidationError):
        InitiateKnowledgeDocumentUploadRequest.model_validate(
            make_payload(resourceType="general")
        )


def test_script_resource_requires_script_genre() -> None:
    with pytest.raises(ValidationError):
        InitiateKnowledgeDocumentUploadRequest.model_validate(
            make_payload(scriptGenre=None)
        )


def test_non_script_resource_ignores_script_genre() -> None:
    payload = InitiateKnowledgeDocumentUploadRequest.model_validate(
        make_payload(resourceType="faq", scriptGenre="horror")
    )

    assert payload.script_genre is None
