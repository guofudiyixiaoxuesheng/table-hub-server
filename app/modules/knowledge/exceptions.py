"""知识库资源上传业务异常。"""

from app.core.exceptions import ApplicationError, ConflictError


class KnowledgeDocumentNotFoundError(ApplicationError):
    status_code = 404
    code = "knowledge_not_found"

    def __init__(self, message: str = "知识库资源或上传会话不存在") -> None:
        super().__init__(message)


class KnowledgeDocumentConflictError(ConflictError):
    code = "knowledge_conflict"


class KnowledgeDocumentUploadError(ApplicationError):
    status_code = 422
    code = "knowledge_upload_invalid"
