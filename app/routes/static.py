"""静态文件与页面接口：主页、属性页、静态资源（无 static 前缀）。"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette import status

from app.config import get_config
from app.utils.errors import InvalidPathError, NotFoundError

router = APIRouter(tags=["static"])

_INDEX_HTML_NAME: str = "index.html"


@router.get("/", status_code=status.HTTP_200_OK, include_in_schema=False)
def home_page() -> FileResponse:
    """文件管理器主页。"""
    return FileResponse(_index_html_path())


@router.get("/metadata", status_code=status.HTTP_200_OK, include_in_schema=False)
def metadata_page() -> FileResponse:
    """条目属性页（前端根据 URL 渲染不同视图）。"""
    return FileResponse(_index_html_path())


@router.get("/{resource_path:path}", status_code=status.HTTP_200_OK, include_in_schema=False)
def serve_static_resource(resource_path: str) -> FileResponse:
    """提供 static 目录下的静态资源（css/js/html 等）。"""
    static_root: Path = _static_root_path()
    candidate: Path = (static_root / resource_path).resolve()
    if candidate != static_root and not candidate.is_relative_to(static_root):
        raise InvalidPathError("静态资源路径非法")

    if not candidate.is_file():
        raise NotFoundError(f"静态资源不存在: /{resource_path}")

    return FileResponse(candidate)


def _static_root_path() -> Path:
    """返回静态资源根目录（已创建）。"""
    static_root: Path = Path(get_config().static_dir).expanduser().resolve()
    static_root.mkdir(parents=True, exist_ok=True)
    return static_root


def _index_html_path() -> Path:
    """返回主页 HTML 文件路径，缺失时抛出 404。"""
    index_path: Path = _static_root_path() / "html" / _INDEX_HTML_NAME
    if not index_path.is_file():
        raise NotFoundError("主页文件缺失")
    return index_path
