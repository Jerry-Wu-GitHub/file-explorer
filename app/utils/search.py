"""目录树递归搜索。"""

import os
from pathlib import Path
from typing import Optional

from app.constants.pagination import SEARCH_MAX_DEPTH, SEARCH_MAX_ENTRIES
from app.models.fs_entry import FsEntry
from app.utils.errors import ForbiddenError, NotFoundError, ValidationFailedError
from app.utils.fs_utils import build_entry, join_virtual_path
from app.utils.path_utils import resolve_path, validate_relative_path


def search_files(
    virtual_path: str,
    follow_link: bool,
    *,
    query: Optional[str],
    filter_type: str,
    min_size: Optional[int],
    max_size: Optional[int],
    modified_after: Optional[float],
    modified_before: Optional[float],
    page: int,
    size: int,
) -> tuple[list[FsEntry], int]:
    """递归搜索起始目录下的条目，应用过滤并分页，返回（条目列表, 总数）。"""
    normalized: str = validate_relative_path(virtual_path)
    target: Path = resolve_path(normalized, follow_link=follow_link)
    if not os.path.exists(target):
        raise NotFoundError(f"路径不存在: {normalized}")
    if not os.path.isdir(target):
        raise ValidationFailedError("搜索起始路径不是目录")

    keyword: Optional[str] = query.strip().lower() if query else None

    matched: list[FsEntry] = []
    visited_dirs: set[str] = set()
    pending: list[tuple[Path, str, int]] = [(target, normalized, 0)]

    while pending:
        current_path, current_virtual, depth = pending.pop()
        real_key: str = str(current_path.resolve())
        if real_key in visited_dirs:
            continue
        visited_dirs.add(real_key)

        if len(visited_dirs) + len(matched) > SEARCH_MAX_ENTRIES:
            raise ValidationFailedError("搜索结果过大，请缩小搜索范围")

        try:
            iterator = os.scandir(current_path)
        except PermissionError as exc:
            raise ForbiddenError("没有权限访问搜索起始目录") from exc

        try:
            for entry in iterator:
                if entry.name in (".", ".."):
                    continue
                child_path: Path = Path(entry.path)
                child_virtual: str = join_virtual_path(current_virtual, entry.name)

                child_entry: FsEntry = build_entry(child_path, child_virtual, follow_link)

                # 目录（含沙箱内的链接目录）总是继续遍历，无论自身是否匹配
                if child_entry.type == "directory" and depth + 1 < SEARCH_MAX_DEPTH:
                    pending.append((child_path, child_virtual, depth + 1))

                if not _matches(child_entry, keyword, filter_type, min_size, max_size,
                                modified_after, modified_before):
                    continue
                matched.append(child_entry)
        finally:
            iterator.close()

    matched.sort(key=_name_key)
    total: int = len(matched)
    start_index: int = (page - 1) * size
    return matched[start_index : start_index + size], total


def _name_key(entry: FsEntry) -> str:
    """按名称忽略大小写排序的键。"""
    return entry.name.casefold()


def _matches(
    entry: FsEntry,
    keyword: Optional[str],
    filter_type: str,
    min_size: Optional[int],
    max_size: Optional[int],
    modified_after: Optional[float],
    modified_before: Optional[float],
) -> bool:
    """判断条目是否满足全部过滤条件。"""
    if keyword is not None and keyword not in entry.name.casefold():
        return False
    if filter_type != "all" and entry.type != filter_type:
        return False
    if min_size is not None and entry.size < min_size:
        return False
    if max_size is not None and entry.size > max_size:
        return False
    if modified_after is not None and entry.modified_at < modified_after:
        return False
    if modified_before is not None and entry.modified_at > modified_before:
        return False
    return True
