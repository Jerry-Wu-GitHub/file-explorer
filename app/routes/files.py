"""文件系统 API 路由。

本模块提供目录列出、元数据查询、创建文件、删除、修改元数据以及
复制等接口。所有成功响应使用 :class:`ApiResponse`，所有失败响应
由全局异常处理器统一转换为 :class:`ErrorResponse`。
"""

import logging
from email.utils import formatdate
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from starlette import status

from app.dependencies.services import (
    get_archive_service,
    get_content_service,
    get_file_service,
    get_modify_service,
    get_small_file_upload_service,
    get_write_service,
)
from app.services.archive_service import (
    ArchiveService,
    iter_archive_stream,
)
from app.errors.exceptions import (
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_CONFLICT,
    HTTP_STATUS_CONTENT_TOO_LARGE,
    HTTP_STATUS_FORBIDDEN,
    HTTP_STATUS_INTERNAL_SERVER_ERROR,
    HTTP_STATUS_NOT_FOUND,
    HTTP_STATUS_RANGE_NOT_SATISFIABLE,
    HTTP_STATUS_UNPROCESSABLE_CONTENT,
)
from app.schemas.base import ApiResponse, ErrorResponse
from app.schemas.filesystem import (
    FileSystemEntryMetadata,
    ListDirectoryQuery,
)
from app.schemas.write import (
    CopyEntryRequest,
    CreateFileRequest,
    UpdateMetadataRequest,
)
from app.services.content_service import ContentService
from app.services.file_service import FileService
from app.services.modify_service import ModifyService
from app.services.write_service import WriteService
from app.services.small_file_upload_service import SmallFileUploadService
from app.utils.content_disposition import build_content_disposition
from app.utils.file_stream import iter_file_range
from app.utils.http_range import RangeStatus


logger = logging.getLogger(__name__)


router = APIRouter()
"""文件系统 API 路由对象。"""


COMMON_ERROR_RESPONSES: dict[int | str, dict] = {
    HTTP_STATUS_BAD_REQUEST: {"model": ErrorResponse},
    HTTP_STATUS_FORBIDDEN: {"model": ErrorResponse},
    HTTP_STATUS_NOT_FOUND: {"model": ErrorResponse},
    HTTP_STATUS_CONFLICT: {"model": ErrorResponse},
    HTTP_STATUS_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    HTTP_STATUS_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
}


CONTENT_ERROR_RESPONSES: dict[int | str, dict] = {
    **COMMON_ERROR_RESPONSES,
    HTTP_STATUS_RANGE_NOT_SATISFIABLE: {
        "model": ErrorResponse,
        "description": "Range 无效",
    },
}
"""文件接口共享的 OpenAPI 错误响应声明。"""


# -------- 只读接口 --------


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[list[FileSystemEntryMetadata]],
    responses=COMMON_ERROR_RESPONSES,
    summary="列出目录内容",
)
def list_directory(
    query: Annotated[ListDirectoryQuery, Depends()],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> ApiResponse[list[FileSystemEntryMetadata]]:
    """列出目录内容。"""
    entries, total = file_service.list_directory(
        virtual_path=query.path,
        page=query.page,
        size=query.size,
        sort=query.sort,
        filter_type=query.type,
        follow_link=query.follow_link,
    )
    return ApiResponse[list[FileSystemEntryMetadata]](
        data=entries,
        meta={"total": total, "page": query.page, "size": query.size},
    )


@router.get(
    "/metadata",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[FileSystemEntryMetadata],
    responses=COMMON_ERROR_RESPONSES,
    summary="获取元数据",
)
def get_metadata(
    path: Annotated[str, Query(description="目标沙箱虚拟路径")] = "/",
    follow_link: Annotated[
        bool, Query(alias="followLink", description="是否跟随符号链接")
    ] = True,
    file_service: FileService = Depends(get_file_service),
) -> ApiResponse[FileSystemEntryMetadata]:
    """获取文件或目录的元数据。"""
    metadata = file_service.get_metadata(path, follow_link=follow_link)
    return ApiResponse[FileSystemEntryMetadata](data=metadata)


# -------- 创建文件 --------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FileSystemEntryMetadata],
    responses=COMMON_ERROR_RESPONSES,
    summary="创建空文件",
)
def create_file(
    payload: Annotated[CreateFileRequest, Body()],
    write_service: Annotated[WriteService, Depends(get_write_service)],
) -> ApiResponse[FileSystemEntryMetadata]:
    """创建空文件。"""
    metadata = write_service.create_file(payload.path)
    return ApiResponse[FileSystemEntryMetadata](data=metadata)


# -------- 删除 --------


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=COMMON_ERROR_RESPONSES,
    summary="删除文件或目录",
)
def delete_entry(
    path: Annotated[str, Query(description="要删除的沙箱虚拟路径")],
    recursive: Annotated[bool, Query(description="目录非空时是否递归删除")] = False,
    follow_link: Annotated[
        bool, Query(alias="followLink", description="是否跟随符号链接")
    ] = True,
    write_service: WriteService = Depends(get_write_service),
) -> Response:
    """删除文件、目录或符号链接。"""
    write_service.delete_entry(
        path, recursive=recursive, follow_link=follow_link
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------- 修改元数据 --------


@router.patch(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[FileSystemEntryMetadata],
    responses=COMMON_ERROR_RESPONSES,
    summary="修改元数据",
)
def update_metadata(
    payload: Annotated[UpdateMetadataRequest, Body()],
    path: Annotated[str, Query(description="目标沙箱虚拟路径")],
    follow_link: Annotated[
        bool, Query(alias="followLink", description="是否跟随符号链接")
    ] = True,
    modify_service: ModifyService = Depends(get_modify_service),
) -> ApiResponse[FileSystemEntryMetadata]:
    """修改文件或目录的元数据。"""
    metadata = modify_service.update_metadata(
        path, payload, follow_link=follow_link
    )
    return ApiResponse[FileSystemEntryMetadata](data=metadata)


# -------- 复制 --------


@router.post(
    "/copy",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FileSystemEntryMetadata],
    responses=COMMON_ERROR_RESPONSES,
    summary="复制文件或文件夹",
)
def copy_entry(
    payload: Annotated[CopyEntryRequest, Body()],
    modify_service: Annotated[ModifyService, Depends(get_modify_service)],
) -> ApiResponse[FileSystemEntryMetadata]:
    """复制文件或递归复制文件夹。"""
    metadata = modify_service.copy_entry(
        payload.source, payload.destination, overwrite=payload.overwrite
    )
    return ApiResponse[FileSystemEntryMetadata](data=metadata)


# -------- 下载 --------


@router.get(
    "/content",
    response_class=StreamingResponse,
    responses=CONTENT_ERROR_RESPONSES,
    summary="下载文件内容",
    description=(
        "下载指定文件的完整内容或部分内容。支持 HTTP Range 请求，"
        "返回 200 / 206 / 416 三种状态之一。"
    ),
)
def download_content(
    request: Request,
    path: Annotated[str, Query(description="目标文件的沙箱虚拟路径")],
    follow_link: Annotated[
        bool, Query(alias="followLink", description="是否跟随符号链接")
    ] = True,
    content_service: ContentService = Depends(get_content_service),
) -> Response:
    """下载文件内容。

    根据请求头中的 ``Range`` 字段决定返回完整内容还是部分内容。
    """
    range_header = request.headers.get("Range")
    descriptor = content_service.prepare_content(
        path, follow_link=follow_link, range_header=range_header
    )

    base_headers = {
        "Accept-Ranges": "bytes",
        "ETag": descriptor.etag,
        "Last-Modified": formatdate(descriptor.last_modified, usegmt=True),
        "Content-Disposition": build_content_disposition(descriptor.filename),
    }

    if descriptor.range_result.status == RangeStatus.INVALID:
        base_headers["Content-Range"] = f"bytes */{descriptor.file_size}"
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers=base_headers,
        )

    if descriptor.range_result.status == RangeStatus.VALID:
        range_request = descriptor.range_result.request
        assert range_request is not None  # 由 parse_range_header 保证
        content_length = range_request.end - range_request.start + 1
        base_headers["Content-Length"] = str(content_length)
        base_headers["Content-Range"] = (
            f"bytes {range_request.start}-{range_request.end}"
            f"/{descriptor.file_size}"
        )
        return StreamingResponse(
            iter_file_range(
                descriptor.real_path,
                range_request.start,
                range_request.end,
            ),
            media_type=descriptor.mime_type,
            headers=base_headers,
            status_code=status.HTTP_206_PARTIAL_CONTENT,
        )

    base_headers["Content-Length"] = str(descriptor.file_size)
    return StreamingResponse(
        iter_file_range(descriptor.real_path, 0, descriptor.file_size - 1),
        media_type=descriptor.mime_type,
        headers=base_headers,
        status_code=status.HTTP_200_OK,
    )


ARCHIVE_DEFAULT_FILENAME: str = "archive.zip"
"""压缩包默认下载文件名。"""


@router.get(
    "/download-zip",
    response_class=StreamingResponse,
    responses=COMMON_ERROR_RESPONSES,
    summary="压缩打包下载",
    description=(
        "将多个文件或目录打包为 ZIP 下载。目录会被递归展开；"
        "ZIP 内的路径保留输入的目录结构，以避免同名冲突。"
        "``paths`` 为逗号分隔的沙箱虚拟路径列表。"
    ),
)
def download_zip(
    paths: Annotated[
        str,
        Query(description="逗号分隔的沙箱虚拟路径列表"),
    ],
    follow_link: Annotated[
        bool, Query(alias="followLink", description="是否跟随符号链接")
    ] = True,
    archive_service: ArchiveService = Depends(get_archive_service),
) -> Response:
    """压缩打包下载。"""
    path_list = parse_comma_separated_paths(paths)
    entries = archive_service.prepare_entries(
        path_list, follow_link=follow_link
    )
    return StreamingResponse(
        iter_archive_stream(entries),
        media_type="application/zip",
        headers={
            "Content-Disposition": build_content_disposition(
                ARCHIVE_DEFAULT_FILENAME
            ),
        },
    )


def parse_comma_separated_paths(raw: str) -> list[str]:
    """解析逗号分隔的路径字符串。

    Args:
        raw: 原始查询字符串值。

    Returns:
        去空白后的路径列表，空项被丢弃。
    """
    return [item.strip() for item in raw.split(",") if item.strip()]


# -------- 上传 --------


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[FileSystemEntryMetadata],
    responses={
        **COMMON_ERROR_RESPONSES,
        HTTP_STATUS_CONTENT_TOO_LARGE: {
            "model": ErrorResponse,
            "description": "文件大小超过上限",
        },
    },
    summary="上传小文件",
    description=(
        "以 ``multipart/form-data`` 上传单个文件。``path`` 指定目标"
        "目录，最终文件名取自表单中的 ``file`` 字段；``overwrite`` "
        "控制同名文件是否允许覆盖。上传过程使用临时文件加原子重命名，"
        "避免读到半写文件。"
    ),
)
def upload_small_file(
    path: Annotated[
        str, Query(description="目标目录的沙箱虚拟路径")
    ],
    file: Annotated[
        UploadFile, File(description="要上传的文件内容")
    ],
    overwrite: Annotated[
        bool, Form(description="同名文件是否允许覆盖")
    ] = False,
    upload_service: SmallFileUploadService = Depends(
        get_small_file_upload_service
    ),
) -> ApiResponse[FileSystemEntryMetadata]:
    """上传小文件。"""
    metadata = upload_service.upload_file(
        target_directory_virtual=path,
        filename=file.filename,
        content=file.file,
        overwrite=overwrite,
    )
    return ApiResponse[FileSystemEntryMetadata](data=metadata)


__all__ = ["router"]
