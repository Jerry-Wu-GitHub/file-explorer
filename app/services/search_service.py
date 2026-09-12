"""文件搜索服务。

本模块提供 :class:`SearchService`，在指定目录下递归遍历条目，按
关键词、类型、大小、修改时间过滤，并按名称升序排序后分页返回。
"""

import os
from pathlib import Path

from app.errors import BusinessError, ErrorCode
from app.schemas.filesystem import FileSystemEntryMetadata
from app.schemas.search import SearchQuery
from app.services.file_service import sort_metadata_entries
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.utils.time_utils import datetime_to_timestamp


class SearchService:
    """递归搜索服务。

    Attributes:
        path_service: 沙箱路径解析服务。
        metadata_service: 元数据组装服务。
    """

    def __init__(
        self,
        path_service: PathService,
        metadata_service: MetadataService,
    ) -> None:
        """构造搜索服务。

        Args:
            path_service: 沙箱路径解析服务。
            metadata_service: 元数据组装服务。
        """
        self._path_service: PathService = path_service
        self._metadata_service: MetadataService = metadata_service

    def search(
        self,
        query: SearchQuery,
    ) -> tuple[list[FileSystemEntryMetadata], int]:
        """按查询条件搜索条目。

        结果按名称升序排序后分页。名称比较不区分大小写，同分时按
        原名称排序以保证确定性。

        Args:
            query: 搜索查询参数。

        Returns:
            ``(当前页条目列表, 过滤后的条目总数)``。

        Raises:
            BusinessError: 查询条件非法、起始路径非法、不存在或不是目录。
        """
        self._validate_query(query)
        root_real = self._path_service.resolve_real_path(
            query.path, follow_link=True
        )
        self._ensure_directory(root_real)
        entries = self._collect_entries(root_real, query)
        sorted_entries = sort_metadata_entries(entries, "name", "asc")
        total = len(sorted_entries)
        start = (query.page - 1) * query.size
        end = start + query.size
        return sorted_entries[start:end], total

    def _validate_query(self, query: SearchQuery) -> None:
        """校验查询条件的跨字段约束。

        Args:
            query: 搜索查询参数。

        Raises:
            BusinessError: ``minSize`` 大于 ``maxSize``。
        """
        if query.min_size is not None and query.max_size is not None:
            if query.min_size > query.max_size:
                raise BusinessError(
                    ErrorCode.VALIDATION_ERROR,
                    "minSize 不能大于 maxSize",
                )

    def _ensure_directory(self, real_path: Path) -> None:
        """校验起始路径存在且为目录。"""
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

    def _collect_entries(
        self,
        root_real: Path,
        query: SearchQuery,
    ) -> list[FileSystemEntryMetadata]:
        """递归收集所有满足条件的条目。

        Args:
            root_real: 起始目录真实路径。
            query: 搜索查询参数。

        Returns:
            满足条件的元数据列表。
        """
        entries: list[FileSystemEntryMetadata] = []
        for dirpath, dirnames, filenames in os.walk(
            root_real, followlinks=query.follow_link
        ):
            entries.extend(
                self._process_names(dirpath, list(dirnames), query)
            )
            entries.extend(
                self._process_names(dirpath, list(filenames), query)
            )
        return entries

    def _process_names(
        self,
        dirpath: str,
        names: list[str],
        query: SearchQuery,
    ) -> list[FileSystemEntryMetadata]:
        """处理某目录下的一组条目名称。

        单个条目读取失败（权限不足、路径逃逸等）时静默跳过，避免
        一个异常条目打断整次搜索。

        Args:
            dirpath: 当前目录的真实路径字符串。
            names: 该目录下的条目名称列表。
            query: 搜索查询参数。

        Returns:
            匹配的元数据列表。
        """
        results: list[FileSystemEntryMetadata] = []
        for name in names:
            full_path = Path(dirpath) / name
            try:
                metadata = self._metadata_service.build_metadata(
                    full_path, follow_link=query.follow_link
                )
            except BusinessError:
                continue
            if self._matches(metadata, query):
                results.append(metadata)
        return results

    def _matches(
        self,
        metadata: FileSystemEntryMetadata,
        query: SearchQuery,
    ) -> bool:
        """判断元数据是否满足全部查询条件。"""
        if not self._match_keyword(metadata, query.q):
            return False
        if not self._match_type(metadata, query.type):
            return False
        if not self._match_size(metadata, query.min_size, query.max_size):
            return False
        return self._match_time(
            metadata,
            query.modified_after,
            query.modified_before,
        )

    def _match_keyword(
        self,
        metadata: FileSystemEntryMetadata,
        keyword: str | None,
    ) -> bool:
        """判断条目名称是否包含关键词（不区分大小写）。"""
        if keyword is None or keyword == "":
            return True
        return keyword.casefold() in metadata.name.casefold()

    def _match_type(
        self,
        metadata: FileSystemEntryMetadata,
        filter_type: str,
    ) -> bool:
        """判断条目类型是否匹配。"""
        if filter_type == "all":
            return True
        return metadata.type == filter_type

    def _match_size(
        self,
        metadata: FileSystemEntryMetadata,
        min_size: int | None,
        max_size: int | None,
    ) -> bool:
        """判断条目大小是否在给定范围内（含边界）。"""
        if min_size is not None and metadata.size < min_size:
            return False
        if max_size is not None and metadata.size > max_size:
            return False
        return True

    def _match_time(
        self,
        metadata: FileSystemEntryMetadata,
        modified_after,
        modified_before,
    ) -> bool:
        """判断条目修改时间是否在给定范围内（含边界）。"""
        if modified_after is not None:
            after_ts = datetime_to_timestamp(modified_after)
            if metadata.modified_at < after_ts:
                return False
        if modified_before is not None:
            before_ts = datetime_to_timestamp(modified_before)
            if metadata.modified_at > before_ts:
                return False
        return True


__all__ = ["SearchService"]
