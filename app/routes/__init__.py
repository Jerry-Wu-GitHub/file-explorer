"""路由包：组装 API 路由与静态路由，导出 get_router。"""

from fastapi import APIRouter

from app.routes import api, static


def get_router() -> APIRouter:
    """组装并返回应用根路由。

    - API 路由挂载在 /api/v1 前缀下；
    - 静态路由（主页、属性页、静态资源）挂在根路径，接口本身无 static 前缀。
    """
    root_router = APIRouter()
    root_router.include_router(api.router, prefix="/api/v1")
    root_router.include_router(static.router)
    return root_router
