"""汇总知识库资源路由。"""

from fastapi import APIRouter

from app.api.v1.knowledge.routes.chunk_document import router as chunk_router
from app.api.v1.knowledge.routes.complete_upload import router as complete_router
from app.api.v1.knowledge.routes.delete_document import router as delete_router
from app.api.v1.knowledge.routes.embed_chunks import router as embed_router
from app.api.v1.knowledge.routes.get_manifest import router as manifest_router
from app.api.v1.knowledge.routes.initiate_upload import router as initiate_router
from app.api.v1.knowledge.routes.list_documents import router as list_router
from app.api.v1.knowledge.routes.load_document import router as load_router
from app.api.v1.knowledge.routes.retrieve_chunks import router as retrieve_router

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
router.include_router(initiate_router)
router.include_router(complete_router)
router.include_router(manifest_router)
router.include_router(list_router)
router.include_router(delete_router)
router.include_router(load_router)
router.include_router(chunk_router)
router.include_router(embed_router)
router.include_router(retrieve_router)
