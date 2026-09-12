"""静态资源路由。

本模块挂载前端静态资源目录到 :data:`app.constants.STATIC_PREFIX`
前缀下，使 CSS、JavaScript、图片等资源可以通过 ``/static/...``
访问。

HTML 页面本身不通过本路由暴露；页面路由由 :mod:`main` 显式声明，
以便按名称返回固定文件。
"""

from pathlib import Path

from fastapi import APIRouter
from starlette.staticfiles import StaticFiles

from app.config import get_config
from app.constants import STATIC_PREFIX


router = APIRouter()
"""静态资源路由对象。"""


def mount_static_files(application) -> None:
    """将静态资源目录挂载到 FastAPI 应用。

    目录不存在时不挂载，并在日志中给出提示；避免启动失败。

    Args:
        application: FastAPI 应用实例。
    """
    config = get_config()
    static_directory: Path = config.static_directory
    if not static_directory.is_dir():
        return
    application.mount(
        STATIC_PREFIX,
        StaticFiles(directory=str(static_directory)),
        name="static",
    )


__all__ = ["router", "mount_static_files"]
