"""/api/v1 下的文件类接口（无 /api/v1 前缀）。"""

from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    File,
    Form,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response, StreamingResponse
from starlette import status

from app.models.common import ApiResponse
from app.models.fs_entry import FsEntry
from app.routes.schemas.request import (
    CopyRequest,
    CreateFileRequest,
    CreateFolderRequest,
    PatchMetadataRequest,
)
from app.utils import fs_mutations
from app.utils.download import build_download_response, build_zip_response
from app.utils.errors import ValidationFailedError
from app.utils.fs_utils import get_metadata, list_directory
from app.utils.search import search_files

router = APIRouter(tags=["files"])

_SORT_SEPARATOR: str = ","
_SUPPORTED_SORT_FIELDS: frozenset[str] = frozenset(
    {"name", "size", "modifiedAt", "createdAt", "accessedAt"}
)


def _parse_sort(sort_value: str) -> tuple[str, str]:
    """解析 sort 参数为（字段, 方向）。"""
    parts: list[str] = sort_value.split(_SORT_SEPARATOR)
    if len(parts) != 2:
        raise ValidationFailedError("sort 格式应为 字段,asc|desc")
    field: str = parts[0]
    direction: str = parts[1]
    if field not in _SUPPORTED_SORT_FIELDS:
        raise ValidationFailedError(f"不支持的排序字段: {field}")
    if direction not in ("asc", "desc"):
        raise ValidationFailedError(f"不支持的排序方向: {direction}")
    return field, direction


def _parse_iso_timestamp(value: Optional[str]) -> Optional[float]:
    """解析可选 ISO 8601 时间为时间戳。"""
    if value is None or value == "":
        return None
    try:
        parsed: datetime = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationFailedError(f"时间格式非法: {value}") from exc
    return parsed.timestamp()


@router.get("/files", status_code=status.HTTP_200_OK)
def list_files(
    path: str = Query("/", description="目录路径"),
    page: int = Query(1, description="页码", ge=1),
    size: int = Query(50, description="每页数量", ge=1, le=200),
    sort: str = Query("name,asc", description="排序，如 name,asc"),
    type: str = Query("all", description="过滤类型"),
    follow_link: bool = Query(True, alias="followLink", description="是否跟随符号链接"),
) -> ApiResponse[list[FsEntry]]:
    """列出目录内容。"""
    if type not in ("all", "file", "directory"):
        raise ValidationFailedError(f"不支持的过滤类型: {type}")
    sort_field, sort_direction = _parse_sort(sort)

    entries, total = list_directory(
        path,
        follow_link,
        page=page,
        size=size,
        sort_field=sort_field,
        sort_direction=sort_direction,
        filter_type=type,
    )
    return ApiResponse[list[FsEntry]](data=entries, meta={"total": total, "page": page, "size": size})


@router.get("/files/metadata", status_code=status.HTTP_200_OK)
def fetch_metadata(
    path: str = Query("/", description="目录/文件路径"),
    follow_link: bool = Query(True, alias="followLink", description="是否跟随符号链接"),
) -> ApiResponse[FsEntry]:
    """获取单个条目的元数据。"""
    return ApiResponse[FsEntry](data=get_metadata(path, follow_link))


@router.get("/files/content", status_code=status.HTTP_200_OK)
def download_content(
    request: Request,
    path: str = Query("/", description="目录/文件路径"),
    follow_link: bool = Query(True, alias="followLink", description="是否跟随符号链接"),
) -> StreamingResponse:
    """下载文件，支持 HTTP Range 分块下载。"""
    return build_download_response(path, follow_link, request)


@router.post("/files/upload", status_code=status.HTTP_201_CREATED)
def upload_small_file(
    path: str = Query("/", description="目标目录"),
    overwrite: bool = Form(False, description="是否覆盖同名文件"),
    file: UploadFile = File(..., description="文件内容"),
) -> ApiResponse[FsEntry]:
    """上传小文件（multipart/form-data）。"""
    entry: FsEntry = fs_mutations.upload_small_file(
        path, file.filename or "", file.file, overwrite
    )
    return ApiResponse[FsEntry](data=entry)


@router.post("/files", status_code=status.HTTP_201_CREATED)
def create_file(body: CreateFileRequest) -> ApiResponse[FsEntry]:
    """创建文件；提供 linkTarget 时创建符号链接。"""
    if body.link_target is not None:
        entry: FsEntry = fs_mutations.create_symbolic_link(body.path, body.link_target)
    else:
        entry = fs_mutations.create_file(body.path)
    return ApiResponse[FsEntry](data=entry)


@router.post("/folders", status_code=status.HTTP_201_CREATED)
def create_folder(body: CreateFolderRequest) -> ApiResponse[FsEntry]:
    """创建文件夹。"""
    return ApiResponse[FsEntry](data=fs_mutations.create_directory(body.path))


@router.delete("/files", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    path: str = Query(..., description="要删除的路径"),
    recursive: bool = Query(False, description="删除文件夹时是否递归删除"),
    follow_link: bool = Query(True, alias="followLink", description="是否跟随符号链接"),
) -> Response:
    """删除文件或文件夹。"""
    fs_mutations.delete_path(path, recursive, follow_link)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/files", status_code=status.HTTP_200_OK)
def patch_metadata(
    path: str = Query(..., description="要修改元数据的路径"),
    follow_link: bool = Query(True, alias="followLink", description="是否跟随符号链接"),
    body: PatchMetadataRequest = Body(...),
) -> ApiResponse[FsEntry]:
    """修改条目元数据（重命名、移动、时间、权限、隐藏）。"""
    entry: FsEntry = fs_mutations.update_metadata(
        path,
        follow_link,
        new_name=body.name,
        new_path=body.path,
        modified_at=body.modified_at,
        accessed_at=body.accessed_at,
        permissions=body.permissions,
        is_hidden=body.is_hidden,
    )
    return ApiResponse[FsEntry](data=entry)


@router.get("/files/search", status_code=status.HTTP_200_OK)
def search_files_endpoint(
    q: Optional[str] = Query(None, description="文件名关键词（模糊匹配）"),
    path: str = Query("/", description="搜索起始目录"),
    type: str = Query("all", description="过滤类型"),
    min_size: Optional[int] = Query(None, alias="minSize", description="最小字节数", ge=0),
    max_size: Optional[int] = Query(None, alias="maxSize", description="最大字节数", ge=0),
    modified_after: Optional[str] = Query(None, alias="modifiedAfter", description="ISO 8601 时间"),
    modified_before: Optional[str] = Query(None, alias="modifiedBefore", description="ISO 8601 时间"),
    page: int = Query(1, description="页码", ge=1),
    size: int = Query(20, description="每页数量", ge=1, le=200),
    follow_link: bool = Query(True, alias="followLink", description="是否跟随符号链接"),
) -> ApiResponse[list[FsEntry]]:
    """按条件搜索目录树。"""
    if type not in ("all", "file", "directory"):
        raise ValidationFailedError(f"不支持的过滤类型: {type}")

    entries, total = search_files(
        path,
        follow_link,
        query=q,
        filter_type=type,
        min_size=min_size,
        max_size=max_size,
        modified_after=_parse_iso_timestamp(modified_after),
        modified_before=_parse_iso_timestamp(modified_before),
        page=page,
        size=size,
    )
    return ApiResponse[list[FsEntry]](data=entries, meta={"total": total, "page": page, "size": size})


@router.get("/files/download-zip", status_code=status.HTTP_200_OK)
def download_zip(
    paths: str = Query(..., description="逗号分隔的路径列表"),
    follow_link: bool = Query(True, alias="followLink", description="是否跟随符号链接"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """将多个路径打包为 zip 下载。"""
    path_list: list[str] = [item for item in paths.split(",") if item]
    return build_zip_response(path_list, follow_link, background_tasks)


@router.post("/files/copy", status_code=status.HTTP_201_CREATED)
def copy_file(body: CopyRequest) -> ApiResponse[FsEntry]:
    """复制文件或文件夹（递归）。"""
    return ApiResponse[FsEntry](
        data=fs_mutations.copy_path(body.source, body.destination, body.overwrite)
    )
