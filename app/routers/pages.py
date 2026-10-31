"""HTML 页面路由。

本模块提供 ``/`` 与 ``/metadata`` 两个页面路由，分别返回主页与
属性页面的 HTML 文件。HTML 文件从
:data:`app.config.Config.static_directory` 下的 ``html`` 子目录读取。
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..config import get_config
from ..constants import (
    INDEX_PAGE_FILENAME,
    INDEX_PAGE_ROUTE,
    METADATA_PAGE_FILENAME,
    METADATA_PAGE_ROUTE,
    STATIC_HTML_DIRECTORY_NAME,
)


router = APIRouter()
"""页面路由对象。"""


def read_html_file(filename: str) -> str:
    """读取静态目录下的 HTML 文件。

    Args:
        filename: HTML 文件名。

    Returns:
        HTML 文件内容；文件缺失时返回占位文本。
    """
    config = get_config()
    file_path = config.static_directory / STATIC_HTML_DIRECTORY_NAME / filename
    if not file_path.is_file():
        return f"<h1>页面不存在：{filename}</h1>"
    return file_path.read_text(encoding="utf-8")


@router.get(
    INDEX_PAGE_ROUTE,
    response_class=HTMLResponse,
    include_in_schema=False,
)
def index_page() -> HTMLResponse:
    """返回主页 HTML。

    Returns:
        HTML 响应。
    """
    return HTMLResponse(content=read_html_file(INDEX_PAGE_FILENAME))


@router.get(
    METADATA_PAGE_ROUTE,
    response_class=HTMLResponse,
    include_in_schema=False,
)
def metadata_page() -> HTMLResponse:
    """返回属性页面 HTML。

    Returns:
        HTML 响应。
    """
    return HTMLResponse(content=read_html_file(METADATA_PAGE_FILENAME))


__all__ = ["router", "read_html_file"]
