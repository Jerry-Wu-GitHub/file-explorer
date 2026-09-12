"""业务 API 路由聚合模块。"""

from fastapi import APIRouter

from .files import router as files_router
from .folders import router as folders_router
from .search import router as search_router
from .uploads import router as uploads_router


router = APIRouter()
"""业务 API 路由对象。"""

router.include_router(files_router, prefix="/files")
router.include_router(uploads_router, prefix="/files")
router.include_router(folders_router, prefix="/folders")
router.include_router(search_router, prefix="/files")


__all__ = ["router"]
