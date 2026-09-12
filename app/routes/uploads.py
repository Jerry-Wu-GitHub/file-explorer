"""分片上传的 HTTP 路由。

本模块提供分片上传的五个接口：初始化、查询、上传分片、完成与
取消。所有成功响应使用 :class:`ApiResponse`，所有失败响应由全局
异常处理器统一转换为 :class:`ErrorResponse`。
"""

from tempfile import SpooledTemporaryFile
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Request, Response
from starlette import status

from ..dependencies.services import get_chunked_upload_service
from ..errors.exceptions import (
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_CONFLICT,
    HTTP_STATUS_CONTENT_TOO_LARGE,
    HTTP_STATUS_FORBIDDEN,
    HTTP_STATUS_GONE,
    HTTP_STATUS_INTERNAL_SERVER_ERROR,
    HTTP_STATUS_NOT_FOUND,
    HTTP_STATUS_RANGE_NOT_SATISFIABLE,
    HTTP_STATUS_UNPROCESSABLE_CONTENT,
)
from ..schemas.base import ApiResponse, ErrorResponse
from ..schemas.filesystem import FileSystemEntryMetadata
from ..schemas.upload import (
    CompleteUploadRequest,
    InitializeUploadRequest,
    UploadChunkResponse,
    UploadSessionResponse,
)
from ..services.chunked_upload_service import ChunkedUploadService


router = APIRouter()
"""分片上传路由对象。"""


ERROR_RESPONSES: dict[int | str, dict] = {
    HTTP_STATUS_BAD_REQUEST: {"model": ErrorResponse},
    HTTP_STATUS_FORBIDDEN: {"model": ErrorResponse},
    HTTP_STATUS_NOT_FOUND: {"model": ErrorResponse},
    HTTP_STATUS_CONFLICT: {"model": ErrorResponse},
    HTTP_STATUS_GONE: {"model": ErrorResponse},
    HTTP_STATUS_CONTENT_TOO_LARGE: {"model": ErrorResponse},
    HTTP_STATUS_RANGE_NOT_SATISFIABLE: {"model": ErrorResponse},
    HTTP_STATUS_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    HTTP_STATUS_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}
"""分片上传接口共享的 OpenAPI 错误响应声明。"""


CHUNK_HEADER_CONTENT_MD5: str = "Content-MD5"
"""分片上传可选携带的 MD5 校验头。"""

CHUNK_HEADER_SHA256: str = "X-Chunk-SHA256"
"""分片上传可选携带的 SHA-256 校验头。"""

CHUNK_BODY_BUFFER_SIZE: int = 8 * 1024 * 1024
"""分片请求体的内存缓冲上限（字节），超过后溢出到磁盘。"""


@router.post(
    "/uploads",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[UploadSessionResponse],
    responses=ERROR_RESPONSES,
    summary="初始化分片上传",
    description=(
        "创建分片上传会话并返回会话 ID。初始化不会创建目标文件，"
        "只创建会话元数据与分片临时目录。"
    ),
)
def initialize_upload(
    payload: Annotated[InitializeUploadRequest, Body()],
    chunked_upload_service: Annotated[
        ChunkedUploadService, Depends(get_chunked_upload_service)
    ],
) -> ApiResponse[UploadSessionResponse]:
    """初始化分片上传会话。"""
    response = chunked_upload_service.initialize_upload(payload)
    return ApiResponse[UploadSessionResponse](data=response)


@router.get(
    "/uploads/{upload_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UploadSessionResponse],
    responses=ERROR_RESPONSES,
    summary="查询上传状态",
    description="用于断点续传，返回已上传与缺失分片列表。",
)
def get_upload_status(
    upload_id: Annotated[str, Path(description="上传会话 ID")],
    chunked_upload_service: Annotated[
        ChunkedUploadService, Depends(get_chunked_upload_service)
    ],
) -> ApiResponse[UploadSessionResponse]:
    """查询上传会话状态。"""
    response = chunked_upload_service.get_upload_status(upload_id)
    return ApiResponse[UploadSessionResponse](data=response)


@router.put(
    "/uploads/{upload_id}/chunks/{chunk_number}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[UploadChunkResponse],
    responses=ERROR_RESPONSES,
    summary="上传单个分片",
    description=(
        "以 ``application/octet-stream`` 上传单个分片。可选携带 "
        "``Content-MD5`` 或 ``X-Chunk-SHA256`` 请求头进行校验。"
    ),
)
async def upload_chunk(
    request: Request,
    upload_id: Annotated[str, Path(description="上传会话 ID")],
    chunk_number: Annotated[
        int, Path(description="分片编号，从 0 开始", ge=0)
    ],
    chunked_upload_service: Annotated[
        ChunkedUploadService, Depends(get_chunked_upload_service)
    ],
) -> ApiResponse[UploadChunkResponse]:
    """上传单个分片。"""
    content_md5 = request.headers.get(CHUNK_HEADER_CONTENT_MD5)
    chunk_sha256 = request.headers.get(CHUNK_HEADER_SHA256)

    with SpooledTemporaryFile(max_size=CHUNK_BODY_BUFFER_SIZE) as buffer:
        async for block in request.stream():
            buffer.write(block)
        buffer.seek(0)
        response = chunked_upload_service.upload_chunk(
            upload_id,
            chunk_number,
            buffer,
            content_md5=content_md5,
            chunk_sha256=chunk_sha256,
        )
    return ApiResponse[UploadChunkResponse](data=response)


@router.post(
    "/uploads/{upload_id}/complete",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FileSystemEntryMetadata],
    responses=ERROR_RESPONSES,
    summary="完成分片上传",
    description=(
        "合并所有分片并生成目标文件。重复调用是幂等的，返回现有"
        "文件元数据。"
    ),
)
def complete_upload(
    payload: Annotated[CompleteUploadRequest, Body()],
    upload_id: Annotated[str, Path(description="上传会话 ID")],
    chunked_upload_service: Annotated[
        ChunkedUploadService, Depends(get_chunked_upload_service)
    ],
) -> ApiResponse[FileSystemEntryMetadata]:
    """完成分片上传并生成目标文件。"""
    metadata = chunked_upload_service.complete_upload(upload_id, payload)
    return ApiResponse[FileSystemEntryMetadata](data=metadata)


@router.delete(
    "/uploads/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=ERROR_RESPONSES,
    summary="取消分片上传",
    description=(
        "取消上传并清理临时数据。取消操作幂等：会话不存在或已过期"
        "时同样返回 204。"
    ),
)
def cancel_upload(
    upload_id: Annotated[str, Path(description="上传会话 ID")],
    chunked_upload_service: Annotated[
        ChunkedUploadService, Depends(get_chunked_upload_service)
    ],
) -> Response:
    """取消上传并清理临时数据。"""
    chunked_upload_service.cancel_upload(upload_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
