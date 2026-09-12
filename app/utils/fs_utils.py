"""文件系统条目的读取、目录列表与元数据操作。"""

import os
import stat
from pathlib import Path
from typing import Optional

from app.models.fs_entry import FsEntry, FsEntryType
from app.utils.errors import ForbiddenError, NotFoundError, ValidationFailedError
from app.utils.mime import guess_mime_type
from app.utils.path_utils import is_path_within_sandbox, resolve_path, validate_relative_path
from app.utils.permissions import mode_to_permissions


def join_virtual_path(parent_path: str, name: str) -> str:
    """拼接沙箱虚拟路径。"""
    if parent_path == "/":
        return "/" + name
    return parent_path + "/" + name


def build_entry(target: Path, virtual_path: str, follow_link: bool) -> FsEntry:
    """根据真实路径构建文件系统条目元数据。

    follow_link=True 时若符号链接指向沙箱外，自动降级为 link 类型，
    避免泄露沙箱外目标信息。
    """
    name: str = "/" if virtual_path == "/" else target.name

    follow_stat = None
    if follow_link:
        try:
            follow_stat = target.stat()
        except OSError:
            follow_stat = None
        if follow_stat is not None and not is_path_within_sandbox(target):
            follow_stat = None

    link_stat = target.lstat()

    if follow_stat is not None:
        entry_type: FsEntryType = _classify_stat(follow_stat)
        size: int = follow_stat.st_size if entry_type == "file" else 0
        mode: int = follow_stat.st_mode
    else:
        entry_type = "link"
        size = link_stat.st_size
        mode = link_stat.st_mode

    mime_type: Optional[str] = None
    if entry_type == "file":
        mime_type = guess_mime_type(name)

    return FsEntry(
        name=name,
        path=virtual_path,
        type=entry_type,
        mime_type=mime_type,
        size=size,
        created_at=link_stat.st_ctime,
        modified_at=link_stat.st_mtime,
        accessed_at=link_stat.st_atime,
        permissions=mode_to_permissions(stat.S_IMODE(mode)),
        is_hidden=name.startswith("."),
    )


def _classify_stat(file_stat: os.stat_result) -> FsEntryType:
    """根据 stat 结果判断条目类型。"""
    if stat.S_ISDIR(file_stat.st_mode):
        return "directory"
    if stat.S_ISREG(file_stat.st_mode):
        return "file"
    return "link"


def _name_sort_key(entry: FsEntry) -> str:
    """按名称排序的键，忽略大小写。"""
    return entry.name.casefold()


def _sort_entries(entries: list[FsEntry], sort_field: str, reverse: bool) -> None:
    """按指定字段原地排序。"""
    if sort_field == "name":
        entries.sort(key=_name_sort_key, reverse=reverse)
    elif sort_field == "size":
        entries.sort(key=_size_sort_key, reverse=reverse)
    elif sort_field == "modifiedAt":
        entries.sort(key=_modified_sort_key, reverse=reverse)
    elif sort_field == "createdAt":
        entries.sort(key=_created_sort_key, reverse=reverse)
    elif sort_field == "accessedAt":
        entries.sort(key=_accessed_sort_key, reverse=reverse)
    else:
        raise ValidationFailedError(f"不支持的排序字段: {sort_field}")


def _size_sort_key(entry: FsEntry) -> int:
    """按大小排序的键。"""
    return entry.size


def _modified_sort_key(entry: FsEntry) -> float:
    """按修改时间排序的键。"""
    return entry.modified_at


def _created_sort_key(entry: FsEntry) -> float:
    """按创建时间排序的键。"""
    return entry.created_at


def _accessed_sort_key(entry: FsEntry) -> float:
    """按访问时间排序的键。"""
    return entry.accessed_at


def get_metadata(virtual_path: str, follow_link: bool) -> FsEntry:
    """获取单个条目的元数据，不存在时抛出 404。"""
    normalized: str = validate_relative_path(virtual_path)
    target: Path = resolve_path(normalized, follow_link)
    if not os.path.lexists(target):
        raise NotFoundError(f"路径不存在: {normalized}")
    return build_entry(target, normalized, follow_link)


def _list_raw_entries(
    target: Path, virtual_path: str, follow_link: bool
) -> list[FsEntry]:
    """列出目录下的全部条目（不排序、不过滤、不分页）。"""
    try:
        iterator = os.scandir(target)
    except PermissionError as exc:
        raise ForbiddenError("没有权限访问该目录") from exc
    except FileNotFoundError as exc:
        raise NotFoundError("目录不存在") from exc
    except NotADirectoryError as exc:
        raise ValidationFailedError("目标路径不是目录") from exc

    entries: list[FsEntry] = []
    try:
        for entry in iterator:
            if entry.name in (".", ".."):
                continue
            child_virtual: str = join_virtual_path(virtual_path, entry.name)
            child: FsEntry = build_entry(Path(entry.path), child_virtual, follow_link)
            entries.append(child)
    finally:
        iterator.close()
    return entries


def list_directory(
    virtual_path: str,
    follow_link: bool,
    *,
    page: int,
    size: int,
    sort_field: str,
    sort_direction: str,
    filter_type: str,
) -> tuple[list[FsEntry], int]:
    """列出目录内容并应用过滤、排序、分页，返回（条目列表, 总数）。"""
    normalized: str = validate_relative_path(virtual_path)
    target: Path = resolve_path(normalized, follow_link)

    entries: list[FsEntry] = _list_raw_entries(target, normalized, follow_link)

    if filter_type != "all":
        entries = [entry for entry in entries if entry.type == filter_type]

    reverse: bool = sort_direction == "desc"
    _sort_entries(entries, sort_field, reverse)

    total: int = len(entries)
    start_index: int = (page - 1) * size
    paged_entries: list[FsEntry] = entries[start_index : start_index + size]
    return paged_entries, total
