"""文件系统写操作服务（创建与删除）。

本模块提供 :class:`WriteService`，负责创建空文件、创建文件夹以及
删除文件 / 目录 / 符号链接。所有路径都经过
:class:`app.services.path_service.PathService` 解析并校验沙箱边界。
"""

import shutil
from pathlib import Path

from ..errors import BusinessError, ErrorCode
from ..schemas.filesystem import FileSystemEntryMetadata
from .metadata_service import MetadataService
from .path_service import PathService


class WriteService:
    """创建与删除操作服务。

    Attributes:
        path_service: 沙箱路径解析服务。
        metadata_service: 元数据组装服务。
    """

    def __init__(
        self,
        path_service: PathService,
        metadata_service: MetadataService,
    ) -> None:
        """构造写服务。

        Args:
            path_service: 沙箱路径解析服务。
            metadata_service: 元数据组装服务。
        """
        self._path_service: PathService = path_service
        self._metadata_service: MetadataService = metadata_service

    def create_file(self, virtual_path: str) -> FileSystemEntryMetadata:
        """创建空文件。

        Args:
            virtual_path: 目标文件的沙箱虚拟路径。

        Returns:
            新文件的元数据。

        Raises:
            BusinessError: 路径非法、父目录缺失、目标已存在或创建失败。
        """
        real_path = self._prepare_new_entry_path(virtual_path)
        try:
            real_path.touch(exist_ok=False)
        except FileExistsError as exc:
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"文件已存在：{real_path.name}",
            ) from exc
        except PermissionError as exc:
            raise BusinessError(
                ErrorCode.FORBIDDEN,
                f"权限不足：{real_path.name}",
            ) from exc
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"创建文件失败：{real_path.name}",
            ) from exc
        return self._metadata_service.build_metadata(real_path, follow_link=True)

    def create_folder(self, virtual_path: str) -> FileSystemEntryMetadata:
        """创建文件夹。

        Args:
            virtual_path: 目标文件夹的沙箱虚拟路径。

        Returns:
            新文件夹的元数据。

        Raises:
            BusinessError: 路径非法、父目录缺失、目标已存在或创建失败。
        """
        real_path = self._prepare_new_entry_path(virtual_path)
        try:
            real_path.mkdir()
        except FileExistsError as exc:
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目录已存在：{real_path.name}",
            ) from exc
        except PermissionError as exc:
            raise BusinessError(
                ErrorCode.FORBIDDEN,
                f"权限不足：{real_path.name}",
            ) from exc
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"创建目录失败：{real_path.name}",
            ) from exc
        return self._metadata_service.build_metadata(real_path, follow_link=True)

    def delete_entry(
        self,
        virtual_path: str,
        recursive: bool = False,
        follow_link: bool = True,
    ) -> None:
        """删除文件、目录或符号链接。

        当 ``follow_link=True`` 且最终段为符号链接时，删除目标是
        链接所指向的对象；当 ``follow_link=False`` 时，仅删除符号
        链接本身。

        Args:
            virtual_path: 要删除的沙箱虚拟路径。
            recursive: 目录非空时是否递归删除。
            follow_link: 是否跟随最终段的符号链接。

        Raises:
            BusinessError: 路径非法、不存在、目录非空或删除失败。
        """
        real_path = self._path_service.resolve_real_path(
            virtual_path, follow_link=follow_link
        )
        if not real_path.exists() and not real_path.is_symlink():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"路径不存在：{virtual_path}",
            )

        if real_path.is_symlink():
            self._remove_symlink(real_path)
            return

        if real_path.is_dir():
            if recursive:
                self._remove_directory_recursive(real_path)
            else:
                self._remove_empty_directory(real_path)
            return

        self._remove_file(real_path)

    def _prepare_new_entry_path(self, virtual_path: str) -> Path:
        """为创建操作准备目标路径并校验前提条件。

        Args:
            virtual_path: 目标沙箱虚拟路径。

        Returns:
            通过校验的目标真实路径。

        Raises:
            BusinessError: 路径非法、父目录缺失或目标已存在。
        """
        real_path = self._path_service.resolve_real_path(
            virtual_path, follow_link=False
        )
        self._path_service.ensure_parent_exists(real_path)
        if real_path.exists() or real_path.is_symlink():
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标已存在：{real_path.name}",
            )
        return real_path

    def _remove_symlink(self, real_path: Path) -> None:
        """删除符号链接本身。"""
        try:
            real_path.unlink()
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"删除符号链接失败：{real_path.name}",
            ) from exc

    def _remove_directory_recursive(self, real_path: Path) -> None:
        """递归删除目录及其全部内容。"""
        try:
            shutil.rmtree(real_path)
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"递归删除目录失败：{real_path.name}",
            ) from exc

    def _remove_empty_directory(self, real_path: Path) -> None:
        """删除空目录，非空时抛出 ``DIRECTORY_NOT_EMPTY``。"""
        if any(real_path.iterdir()):
            raise BusinessError(
                ErrorCode.DIRECTORY_NOT_EMPTY,
                f"目录非空：{real_path.name}",
            )
        try:
            real_path.rmdir()
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"删除目录失败：{real_path.name}",
            ) from exc

    def _remove_file(self, real_path: Path) -> None:
        """删除普通文件。"""
        try:
            real_path.unlink()
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"删除文件失败：{real_path.name}",
            ) from exc


__all__ = ["WriteService"]
