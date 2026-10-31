"""搜索 API 路由。

本模块提供 ``GET /files/search`` 接口，在指定目录下递归搜索文件
与目录。所有成功响应使用 :class:`ApiResponse`，所有失败响应由
全局异常处理器统一转换为 :class:`ErrorResponse`。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette import status

from ..dependencies.services import get_search_service
from ..errors.exceptions import (
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_FORBIDDEN,
    HTTP_STATUS_INTERNAL_SERVER_ERROR,
    HTTP_STATUS_NOT_FOUND,
    HTTP_STATUS_UNPROCESSABLE_CONTENT,
)
from ..schemas.base import ApiResponse, ErrorResponse
from ..schemas.filesystem import FileSystemEntryMetadata
from ..schemas.search import SearchQuery
from ..services.search_service import SearchService


router = APIRouter()
"""搜索 API 路由对象。"""


ERROR_RESPONSES: dict[int | str, dict] = {
    HTTP_STATUS_BAD_REQUEST: {"model": ErrorResponse},
    HTTP_STATUS_FORBIDDEN: {"model": ErrorResponse},
    HTTP_STATUS_NOT_FOUND: {"model": ErrorResponse},
    HTTP_STATUS_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    HTTP_STATUS_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}
"""搜索接口共享的 OpenAPI 错误响应声明。"""


@router.get(
    "/search",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[FileSystemEntryMetadata]],
    responses=ERROR_RESPONSES,
    summary="搜索文件与目录",
    description=(
        "在指定目录下递归搜索条目，支持关键词、类型、大小与修改"
        "时间过滤。多个条件之间为「与」关系。结果按名称升序排序。"
    ),
)
def search_entries(
    query: Annotated[SearchQuery, Depends()],
    search_service: Annotated[SearchService, Depends(get_search_service)],
) -> ApiResponse[list[FileSystemEntryMetadata]]:
    """在指定目录下递归搜索条目。"""
    entries, total = search_service.search(query)
    return ApiResponse[list[FileSystemEntryMetadata]](
        data=entries,
        meta={
            "total": total,
            "page": query.page,
            "size": query.size,
        },
    )


__all__ = ["router"]
