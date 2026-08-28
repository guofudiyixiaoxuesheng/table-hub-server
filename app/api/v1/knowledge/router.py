"""汇总知识库资源路由。"""

from fastapi import APIRouter

from app.api.v1.knowledge.routes.complete_upload import router as complete_router
from app.api.v1.knowledge.routes.get_manifest import router as manifest_router
from app.api.v1.knowledge.routes.initiate_upload import router as initiate_router
from app.api.v1.knowledge.routes.list_documents import router as list_router

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
router.include_router(initiate_router)
router.include_router(complete_router)
router.include_router(manifest_router)
router.include_router(list_router)
