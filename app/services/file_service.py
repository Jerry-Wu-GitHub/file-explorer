"""目录列表与元数据查询服务。

本模块提供 :class:`FileService`，负责在沙箱内列出目录内容与获取
单个条目的元数据。列表操作包含过滤、排序与分页；排序表达式、
过滤类型等参数的合法性在服务层校验。
"""

import os
from pathlib import Path
from typing import Any, Optional

from app.constants import SUPPORTED_SORT_FIELDS, SUPPORTED_SORT_ORDERS
from app.errors import BusinessError, ErrorCode
from app.schemas.filesystem import FileSystemEntryMetadata
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService


def parse_sort_expression(expression: str) -> tuple[str, str]:
    """解析 ``'<字段>,<方向>'`` 形式的排序表达式。

    Args:
        expression: 排序表达式字符串。

    Returns:
        解析后的 ``(字段, 方向)`` 元组。

    Raises:
        BusinessError: 表达式格式错误、字段或方向不受支持。
    """
    parts = expression.split(",")
    if len(parts) != 2:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"排序表达式格式错误：'{expression}'，应为 '<字段>,<方向>'",
        )
    field = parts[0].strip()
    direction = parts[1].strip().lower()
    if field not in SUPPORTED_SORT_FIELDS:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"不支持的排序字段：'{field}'",
        )
    if direction not in SUPPORTED_SORT_ORDERS:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"不支持的排序方向：'{direction}'",
        )
    return field, direction


def build_sort_key(entry: FileSystemEntryMetadata, field: str) -> Any:
    """为给定元数据条目构造排序键。

    ``name`` 字段使用不区分大小写的键，并在大小写相同时以原名称
    作为次要键，确保跨平台排序结果一致。

    Args:
        entry: 元数据条目。
        field: 排序字段。

    Returns:
        可直接用于比较的排序键。
    """
    if field == "name":
        return (entry.name.casefold(), entry.name)
    if field == "size":
        return entry.size
    if field == "modifiedAt":
        return entry.modified_at
    if field == "createdAt":
        return entry.created_at
    if field == "accessedAt":
        return entry.accessed_at
    if field == "type":
        return entry.type
    return (entry.name.casefold(), entry.name)


def sort_metadata_entries(
    entries: list[FileSystemEntryMetadata],
    field: str,
    direction: str,
) -> list[FileSystemEntryMetadata]:
    """按指定字段与方向排序元数据列表。

    Args:
        entries: 待排序的元数据列表。
        field: 排序字段。
        direction: 排序方向，``asc`` 或 ``desc``。

    Returns:
        排序后的新列表。
    """
    sorted_entries = list(entries)
    sorted_entries.sort(
        key=lambda item: build_sort_key(item, field),
        reverse=(direction == "desc"),
    )
    return sorted_entries


class FileService:
    """目录列表与元数据查询服务。

    Attributes:
        path_service: 沙箱路径解析服务。
        metadata_service: 元数据组装服务。
    """

    def __init__(
        self,
        path_service: PathService,
        metadata_service: MetadataService,
    ) -> None:
        """构造文件服务。

        Args:
            path_service: 沙箱路径解析服务。
            metadata_service: 元数据组装服务。
        """
        self._path_service: PathService = path_service
        self._metadata_service: MetadataService = metadata_service

    def list_directory(
        self,
        virtual_path: str,
        page: int = 1,
        size: int = 50,
        sort: str = "name,asc",
        filter_type: str = "all",
        follow_link: bool = True,
        show_hidden: bool = True,
    ) -> tuple[list[FileSystemEntryMetadata], int]:
        """列出目录内容。

        Args:
            virtual_path: 目录的沙箱虚拟路径。
            page: 页码，从 1 开始。
            size: 每页条目数量。
            sort: 排序表达式，例如 ``name,asc``。
            filter_type: 过滤类型，``all`` / ``file`` / ``directory``。
            follow_link: 是否跟随条目的符号链接。
            show_hidden: 是否显示隐藏项目。

        Returns:
            ``(当前页条目列表, 过滤后的条目总数)``。

        Raises:
            BusinessError: 路径非法、不存在、不是目录或排序表达式非法。
        """
        real_path = self._path_service.resolve_real_path(
            virtual_path,
            follow_link=True,
        )
        self._ensure_directory(real_path)
        entries = self._read_directory_entries(
            real_path, filter_type, follow_link, show_hidden
        )
        sort_field, sort_direction = parse_sort_expression(sort)
        sorted_entries = sort_metadata_entries(
            entries, sort_field, sort_direction
        )
        total = len(sorted_entries)
        start = (page - 1) * size
        end = start + size
        return sorted_entries[start:end], total

    def get_metadata(
        self,
        virtual_path: str,
        follow_link: bool = True,
    ) -> FileSystemEntryMetadata:
        """获取文件或目录的元数据。

        Args:
            virtual_path: 文件或目录的沙箱虚拟路径。
            follow_link: 是否跟随符号链接。

        Returns:
            组装完成的 :class:`FileSystemEntryMetadata`。

        Raises:
            BusinessError: 路径非法或目标不存在。
        """
        real_path = self._path_service.resolve_real_path(
            virtual_path,
            follow_link=follow_link,
        )
        return self._metadata_service.build_metadata(
            real_path,
            follow_link=follow_link,
        )

    def _ensure_directory(self, real_path: Path) -> None:
        """校验真实路径存在且为目录。

        Args:
            real_path: 待校验的真实路径。

        Raises:
            BusinessError: 路径不存在或不是目录。
        """
        if not real_path.exists():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"目录不存在：{real_path.name}",
            )
        if not real_path.is_dir():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"路径不是目录：{real_path.name}",
            )

    def _read_directory_entries(
        self,
        directory: Path,
        filter_type: str,
        follow_link: bool,
        show_hidden: bool,
    ) -> list[FileSystemEntryMetadata]:
        """读取目录下的所有匹配条目。

        Args:
            directory: 目录的真实路径。
            filter_type: 过滤类型。
            follow_link: 是否跟随符号链接。
            show_hidden: 是否包含隐藏项目。

        Returns:
            元数据条目列表。
        """
        entries: list[FileSystemEntryMetadata] = []
        with os.scandir(directory) as iterator:
            for dir_entry in iterator:
                metadata = self._read_single_entry(
                    dir_entry, filter_type, follow_link, show_hidden
                )
                if metadata is not None:
                    entries.append(metadata)
        return entries

    def _read_single_entry(
        self,
        dir_entry: os.DirEntry,
        filter_type: str,
        follow_link: bool,
        show_hidden: bool,
    ) -> Optional[FileSystemEntryMetadata]:
        """读取单个目录条目的元数据。

        隐藏过滤、类型过滤或读取失败时返回 ``None``，从而不影响
        整个目录的列出。

        Args:
            dir_entry: :mod:`os` 提供的目录条目。
            filter_type: 过滤类型。
            follow_link: 是否跟随符号链接。
            show_hidden: 是否包含隐藏项目。

        Returns:
            元数据条目；被过滤或读取失败时返回 ``None``。
        """
        if not show_hidden and dir_entry.name.startswith("."):
            return None
        try:
            metadata = self._metadata_service.build_metadata(
                Path(dir_entry.path),
                follow_link=follow_link,
            )
        except BusinessError:
            return None
        if filter_type != "all" and metadata.type != filter_type:
            return None
        return metadata


__all__ = [
    "FileService",
    "parse_sort_expression",
    "build_sort_key",
    "sort_metadata_entries",
]
