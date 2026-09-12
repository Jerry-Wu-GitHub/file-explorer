"""文件夹 API 路由。

本模块提供创建文件夹接口，独立于 ``/files`` 前缀以便与提示中
``POST /folders`` 的路径保持一致。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from starlette import status

from ..dependencies.services import get_write_service
from ..errors.exceptions import (
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_CONFLICT,
    HTTP_STATUS_FORBIDDEN,
    HTTP_STATUS_INTERNAL_SERVER_ERROR,
    HTTP_STATUS_NOT_FOUND,
    HTTP_STATUS_UNPROCESSABLE_CONTENT,
)
from ..schemas.base import ApiResponse, ErrorResponse
from ..schemas.filesystem import FileSystemEntryMetadata
from ..schemas.write import CreateFolderRequest
from ..services.write_service import WriteService


router = APIRouter()
"""文件夹 API 路由对象。"""


ERROR_RESPONSES: dict[int | str, dict] = {
    HTTP_STATUS_BAD_REQUEST: {"model": ErrorResponse},
    HTTP_STATUS_FORBIDDEN: {"model": ErrorResponse},
    HTTP_STATUS_NOT_FOUND: {"model": ErrorResponse},
    HTTP_STATUS_CONFLICT: {"model": ErrorResponse},
    HTTP_STATUS_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    HTTP_STATUS_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}
"""文件夹接口共享的 OpenAPI 错误响应声明。"""


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FileSystemEntryMetadata],
    responses=ERROR_RESPONSES,
    summary="创建文件夹",
)
def create_folder(
    payload: Annotated[CreateFolderRequest, Body()],
    write_service: Annotated[WriteService, Depends(get_write_service)],
) -> ApiResponse[FileSystemEntryMetadata]:
    """创建文件夹。"""
    metadata = write_service.create_folder(payload.path)
    return ApiResponse[FileSystemEntryMetadata](data=metadata)


__all__ = ["router"]
