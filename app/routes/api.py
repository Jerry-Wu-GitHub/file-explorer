"""API 路由聚合：挂载 /api/v1 下的全部接口（无 /api/v1 前缀）。"""

from fastapi import APIRouter

from app.routes import files, uploads

router = APIRouter()

router.include_router(files.router)
router.include_router(uploads.router)
