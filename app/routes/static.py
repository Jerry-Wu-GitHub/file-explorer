"""静态资源路由。

本模块挂载前端静态资源目录到 :data:`app.constants.STATIC_PREFIX`
前缀下，使 CSS、JavaScript、图片等资源可以通过 ``/static/...``
访问。

HTML 页面本身不通过本路由暴露；页面路由由 :mod:`main` 显式声明，
以便按名称返回固定文件。
"""

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette import status

from ..config import get_config


router = APIRouter()
"""静态资源路由对象。"""


# 挂载整个静态目录，提供 /static/* 访问
@router.get("/{full_path:path}", status_code=status.HTTP_200_OK)
async def serve_static(full_path: str):
    """
    返回前端文件。
    """
    config = get_config()
    # 尝试返回具体文件
    file_path = config.static_directory / full_path
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return {"detail": "File not exist"}


__all__ = ["router"]
