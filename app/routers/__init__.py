"""路由包。

本包负责汇总业务 API、静态文件与页面路由：

- :mod:`app.routes.api`：业务 API，挂载在 ``/api/v1`` 前缀下；
- :mod:`app.routes.static`：静态资源占位路由，真实静态文件由
  ``main.py`` 通过 ``StaticFiles`` 挂载在 ``/static`` 前缀下；
- :mod:`app.routes.pages`：HTML 页面路由，无前缀。
"""

from fastapi import APIRouter

from ..constants import API_PREFIX, STATIC_PREFIX
from .api import router as api_router
from .pages import router as pages_router
from .static import router as static_router


def get_router(**kwargs) -> APIRouter:
    """构建并返回顶层路由对象。

    Returns:
        包含业务 API、静态资源与页面子路由的 :class:`APIRouter` 实例。
    """
    root_router = APIRouter(**kwargs)
    root_router.include_router(api_router, prefix=API_PREFIX)
    root_router.include_router(static_router, prefix=STATIC_PREFIX)
    root_router.include_router(pages_router)
    return root_router


__all__ = ["get_router"]
