import uuid

import pytest

from app.modules.knowledge.exceptions import KnowledgeDocumentUploadError
from app.modules.knowledge.pathing import (
    build_version_prefix,
    normalize_relative_path,
)


def test_normalize_relative_path_preserves_folder_structure() -> None:
    assert normalize_relative_path("剧本/角色/侦探.pdf") == "剧本/角色/侦探.pdf"


@pytest.mark.parametrize(
    "path", ["../secret.txt", "/etc/passwd", "folder/../secret.txt"]
)
def test_normalize_relative_path_rejects_path_traversal(path: str) -> None:
    with pytest.raises(KnowledgeDocumentUploadError):
        normalize_relative_path(path)


def test_version_prefix_uses_stable_ids() -> None:
    store_id, document_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert build_version_prefix(store_id, document_id, version_id) == (
        f"stores/{store_id}/knowledge/{document_id}/versions/{version_id}"
    )
