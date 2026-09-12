"""文件系统元数据组装服务。

本模块提供 :class:`MetadataService`，负责将沙箱内的真实路径与
:class:`os.stat_result` 组装为
:class:`app.routes.schemas.filesystem.FileSystemEntryMetadata`，
并处理符号链接的跟随与不跟随两种模式、隐藏属性判定、MIME 推断
以及权限字符串格式化。
"""

import os
import stat as stat_module
from pathlib import Path

from ..errors import BusinessError, ErrorCode
from ..schemas.filesystem import (
    FileSystemEntryMetadata,
    FileSystemEntryType,
)
from .path_service import PathService
from ..utils.mime_utils import guess_mime_type
from ..utils.permission_utils import format_permissions, is_hidden


class MetadataService:
    """文件系统元数据组装服务。

    Attributes:
        path_service: 用于将真实路径转换为虚拟路径的路径服务。
    """

    def __init__(self, path_service: PathService) -> None:
        """构造元数据服务。

        Args:
            path_service: 沙箱路径解析服务。
        """
        self._path_service: PathService = path_service

    def build_metadata(
        self,
        real_path: Path,
        follow_link: bool = True,
    ) -> FileSystemEntryMetadata:
        """构造给定真实路径的元数据。

        Args:
            real_path: 位于沙箱内的真实路径。
            follow_link: 是否跟随最终段的符号链接。

        Returns:
            组装完成的 :class:`FileSystemEntryMetadata`。

        Raises:
            BusinessError: 路径不存在、无权限或读取失败。
        """
        if follow_link:
            return self._build_followed_metadata(real_path)
        return self._build_unfollowed_metadata(real_path)

    def _build_followed_metadata(
        self,
        real_path: Path,
    ) -> FileSystemEntryMetadata:
        """构造跟随符号链接后的元数据。

        Args:
            real_path: 目标真实路径。

        Returns:
            以链接目标类型呈现的元数据。
        """
        stat_result = self._safe_stat(real_path)
        entry_type = self._determine_entry_type(stat_result)
        return self._compose_metadata(real_path, stat_result, entry_type)

    def _build_unfollowed_metadata(
        self,
        real_path: Path,
    ) -> FileSystemEntryMetadata:
        """构造不跟随符号链接的元数据。

        若最终段是符号链接，则以 ``link`` 类型返回其自身信息。

        Args:
            real_path: 目标真实路径。

        Returns:
            符号链接自身或普通条目的元数据。
        """
        lstat_result = self._safe_lstat(real_path)
        if stat_module.S_ISLNK(lstat_result.st_mode):
            return self._compose_link_metadata(real_path, lstat_result)
        entry_type = self._determine_entry_type(lstat_result)
        return self._compose_metadata(real_path, lstat_result, entry_type)

    def _safe_stat(self, real_path: Path) -> os.stat_result:
        """安全地调用 ``stat``，将异常转换为业务错误。

        Args:
            real_path: 目标真实路径。

        Returns:
            文件系统状态对象。

        Raises:
            BusinessError: 路径不存在、无权限或读取失败。
        """
        try:
            return real_path.stat()
        except FileNotFoundError as exc:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"文件或目录不存在：{real_path.name}",
            ) from exc
        except PermissionError as exc:
            raise BusinessError(
                ErrorCode.FORBIDDEN,
                f"权限不足：{real_path.name}",
            ) from exc
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"读取元数据失败：{real_path.name}",
            ) from exc

    def _safe_lstat(self, real_path: Path) -> os.stat_result:
        """安全地调用 ``lstat``，将异常转换为业务错误。

        Args:
            real_path: 目标真实路径。

        Returns:
            不跟随符号链接的文件系统状态对象。

        Raises:
            BusinessError: 路径不存在、无权限或读取失败。
        """
        try:
            return real_path.lstat()
        except FileNotFoundError as exc:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"文件或目录不存在：{real_path.name}",
            ) from exc
        except PermissionError as exc:
            raise BusinessError(
                ErrorCode.FORBIDDEN,
                f"权限不足：{real_path.name}",
            ) from exc
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"读取元数据失败：{real_path.name}",
            ) from exc

    def _determine_entry_type(
        self,
        stat_result: os.stat_result,
    ) -> FileSystemEntryType:
        """根据 ``st_mode`` 判定条目类型。

        Args:
            stat_result: 文件系统状态对象。

        Returns:
            ``file`` / ``directory`` / ``other`` 之一。
        """
        mode = stat_result.st_mode
        if stat_module.S_ISDIR(mode):
            return "directory"
        if stat_module.S_ISREG(mode):
            return "file"
        return "other"

    def _compose_metadata(
        self,
        real_path: Path,
        stat_result: os.stat_result,
        entry_type: FileSystemEntryType,
    ) -> FileSystemEntryMetadata:
        """组装普通文件、目录或其它条目的元数据。

        Args:
            real_path: 真实路径。
            stat_result: 文件系统状态对象。
            entry_type: 已判定的条目类型。

        Returns:
            组装完成的元数据。
        """
        is_directory = entry_type == "directory"
        return FileSystemEntryMetadata(
            name=real_path.name,
            path=self._path_service.to_virtual_path(real_path),
            type=entry_type,
            mime_type=guess_mime_type(real_path, is_directory),
            size=0 if is_directory else stat_result.st_size,
            created_at=stat_result.st_ctime,
            modified_at=stat_result.st_mtime,
            accessed_at=stat_result.st_atime,
            permissions=format_permissions(stat_result.st_mode),
            is_hidden=is_hidden(real_path.name, real_path),
        )

    def _compose_link_metadata(
        self,
        real_path: Path,
        lstat_result: os.stat_result,
    ) -> FileSystemEntryMetadata:
        """组装符号链接本身的元数据。

        Args:
            real_path: 符号链接真实路径。
            lstat_result: ``lstat`` 返回的状态对象。

        Returns:
            类型为 ``link`` 的元数据。
        """
        return FileSystemEntryMetadata(
            name=real_path.name,
            path=self._path_service.to_virtual_path(real_path),
            type="link",
            mime_type=None,
            size=0,
            created_at=lstat_result.st_ctime,
            modified_at=lstat_result.st_mtime,
            accessed_at=lstat_result.st_atime,
            permissions=format_permissions(lstat_result.st_mode),
            is_hidden=is_hidden(real_path.name, real_path),
        )


__all__ = ["MetadataService"]
