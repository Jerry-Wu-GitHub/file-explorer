"""文件下载：HTTP Range 解析、流式文件响应、压缩包下载。"""

import hashlib
import mimetypes
import os
import posixpath
import tempfile
import zipfile
from email.utils import formatdate
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import quote

from fastapi import BackgroundTasks, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.config import get_config
from app.utils.errors import (
    InvalidPathError,
    NotFoundError,
    RangeNotSatisfiableError,
    ValidationFailedError,
)
from app.utils.path_utils import resolve_path, validate_relative_path

_CHUNK_READ_SIZE: int = 1024 * 1024
_ZIP_TEMP_DIR_NAME: str = "zip"


def parse_range_header(
    range_header: Optional[str], total_size: int
) -> Optional[tuple[int, int]]:
    """解析单个 bytes 范围，返回 (start, end) 闭区间，非法时抛 416。"""
    if range_header is None:
        return None

    if not range_header.startswith("bytes="):
        raise RangeNotSatisfiableError("仅支持 bytes 单位")

    range_spec: str = range_header[len("bytes=") :]
    if "," in range_spec:
        raise RangeNotSatisfiableError("仅支持单个范围请求")

    parts: list[str] = range_spec.split("-", maxsplit=1)
    if len(parts) != 2:
        raise RangeNotSatisfiableError("范围格式非法")

    start_text: str = parts[0].strip()
    end_text: str = parts[1].strip()

    if start_text == "" and end_text == "":
        raise RangeNotSatisfiableError("范围格式非法")

    if start_text == "":
        suffix_length: int = _parse_non_negative_int(end_text)
        if suffix_length <= 0:
            raise RangeNotSatisfiableError("后缀长度必须为正")
        start: int = max(0, total_size - suffix_length)
        end: int = total_size - 1
    else:
        start = _parse_non_negative_int(start_text)
        if end_text == "":
            end = total_size - 1
        else:
            end = _parse_non_negative_int(end_text)

    if start >= total_size or start > end:
        raise RangeNotSatisfiableError("范围超出文件大小")

    if end >= total_size:
        end = total_size - 1
    return start, end


def _parse_non_negative_int(text: str) -> int:
    """解析非负整数，非法时抛 416。"""
    if not text.isdigit():
        raise RangeNotSatisfiableError("范围包含非法字符")
    return int(text)


def _content_disposition(filename: str) -> str:
    """构造 Content-Disposition，兼容中文等非 ASCII 文件名。"""
    ascii_name: str = filename.encode("ascii", "replace").decode("ascii")
    encoded_name: str = quote(filename)
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'


def build_download_response(
    virtual_path: str, follow_link: bool, request: Request
) -> StreamingResponse:
    """构造单个文件的下载响应，支持 HTTP Range。"""
    normalized: str = validate_relative_path(virtual_path)
    target: Path = resolve_path(normalized, follow_link=follow_link)

    if not os.path.lexists(target):
        raise NotFoundError(f"路径不存在: {normalized}")
    if os.path.isdir(target) and not os.path.islink(target):
        raise ValidationFailedError("目标是文件夹，无法下载")
    if os.path.islink(target):
        raise InvalidPathError("followLink=false 时无法下载符号链接内容")

    file_stat = target.stat()
    total_size: int = file_stat.st_size
    etag: str = _make_etag(file_stat)
    last_modified: str = formatdate(file_stat.st_mtime, usegmt=True)

    range_spec: Optional[tuple[int, int]] = parse_range_header(
        request.headers.get("range"), total_size
    )

    common_headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _content_disposition(target.name),
        "Content-Type": _guess_download_mime(target.name),
        "ETag": etag,
        "Last-Modified": last_modified,
    }

    if range_spec is None:
        headers: dict[str, str] = {
            **common_headers,
            "Content-Length": str(total_size),
        }
        return StreamingResponse(
            _stream_file(target, 0, total_size - 1),
            status_code=200,
            headers=headers,
            media_type=headers["Content-Type"],
        )

    start, end = range_spec
    content_length: int = end - start + 1
    headers = {
        **common_headers,
        "Content-Length": str(content_length),
        "Content-Range": f"bytes {start}-{end}/{total_size}",
    }
    return StreamingResponse(
        _stream_file(target, start, end),
        status_code=206,
        headers=headers,
        media_type=headers["Content-Type"],
    )


def _make_etag(file_stat: os.stat_result) -> str:
    """基于大小与修改时间生成弱一致的 ETag。"""
    raw: str = f"{file_stat.st_size}-{int(file_stat.st_mtime)}"
    digest: str = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f'"{digest}"'


def _guess_download_mime(filename: str) -> str:
    """猜测下载文件的 MIME 类型。"""
    guessed: Optional[str] = mimetypes.guess_type(filename)[0]
    return guessed or "application/octet-stream"


def _stream_file(target: Path, start: int, end: int) -> Iterator[bytes]:
    """按闭区间 [start, end] 流式读取文件。"""
    remaining: int = end - start + 1
    with open(target, "rb") as file_handle:
        file_handle.seek(start)
        while remaining > 0:
            read_size: int = min(_CHUNK_READ_SIZE, remaining)
            chunk: bytes = file_handle.read(read_size)
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def build_zip_response(
    virtual_paths: list[str],
    follow_link: bool,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    """将多个路径打包为 zip 返回，临时文件由后台任务删除。"""
    if not virtual_paths:
        raise ValidationFailedError("paths 不能为空")

    resolved_pairs: list[tuple[Path, str]] = []
    for virtual_path in virtual_paths:
        normalized: str = validate_relative_path(virtual_path)
        target: Path = resolve_path(normalized, follow_link=follow_link)
        if not os.path.lexists(target):
            raise NotFoundError(f"路径不存在: {normalized}")
        resolved_pairs.append((target, normalized))

    temp_dir: Path = Path(get_config().upload_temp_root) / _ZIP_TEMP_DIR_NAME
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(dir=temp_dir, suffix=".zip")
    os.close(file_descriptor)
    temp_path: Path = Path(temp_name)

    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for target, normalized in resolved_pairs:
                _add_to_archive(archive, target, normalized)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(_remove_temp_file, temp_path)
    return FileResponse(
        path=str(temp_path),
        media_type="application/zip",
        filename="files.zip",
    )


def _remove_temp_file(temp_path: Path) -> None:
    """删除临时 zip 文件。"""
    temp_path.unlink(missing_ok=True)


def _add_to_archive(
    archive: zipfile.ZipFile,
    target: Path,
    virtual_path: str,
) -> None:
    """将单个路径递归写入 zip 归档。"""
    arc_root: str = virtual_path.lstrip("/") or target.name

    if os.path.isdir(target) and not os.path.islink(target):
        for current_dir, _, file_names in os.walk(target, followlinks=False):
            current_arc: str = _arc_name(current_dir, target, arc_root)
            for file_name in file_names:
                file_path: Path = Path(current_dir) / file_name
                archive.write(file_path, posixpath.join(current_arc, file_name))
        return

    archive.write(target, arc_root)


def _arc_name(current_dir: Path, archive_root: Path, arc_root: str) -> str:
    """计算当前目录在归档中的相对路径。"""
    relative_dir: str = os.path.relpath(current_dir, archive_root)
    if relative_dir == ".":
        return arc_root
    return posixpath.join(arc_root, relative_dir)
