"""文件系统元数据修改与复制服务。

本模块提供 :class:`ModifyService`，负责按需修改文件 / 目录的名称、
路径、时间、权限与隐藏属性，以及复制文件或递归复制文件夹。
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from app.errors import BusinessError, ErrorCode
from app.schemas.filesystem import FileSystemEntryMetadata
from app.schemas.write import UpdateMetadataRequest
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.utils.permission_utils import parse_permissions_string


class ModifyService:
    """元数据修改与复制操作服务。

    Attributes:
        path_service: 沙箱路径解析服务。
        metadata_service: 元数据组装服务。
    """

    def __init__(
        self,
        path_service: PathService,
        metadata_service: MetadataService,
    ) -> None:
        """构造修改服务。

        Args:
            path_service: 沙箱路径解析服务。
            metadata_service: 元数据组装服务。
        """
        self._path_service: PathService = path_service
        self._metadata_service: MetadataService = metadata_service

    def update_metadata(
        self,
        virtual_path: str,
        request: UpdateMetadataRequest,
        follow_link: bool = True,
    ) -> FileSystemEntryMetadata:
        """按需修改元数据。

        Args:
            virtual_path: 目标沙箱虚拟路径。
            request: 修改请求。
            follow_link: 是否跟随符号链接。

        Returns:
            更新后的元数据。

        Raises:
            BusinessError: 路径非法、不存在或修改失败。
        """
        real_path = self._path_service.resolve_real_path(
            virtual_path, follow_link=follow_link
        )
        if not real_path.exists() and not real_path.is_symlink():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"路径不存在：{virtual_path}",
            )

        renamed_path = self._compute_renamed_path(real_path, request)
        if renamed_path is not None and renamed_path != real_path:
            self._rename_entry(real_path, renamed_path)
            real_path = renamed_path

        if request.is_hidden is not None:
            real_path = self._apply_hidden_attribute(
                real_path, request.is_hidden
            )

        if request.modified_at is not None or request.accessed_at is not None:
            self._apply_times(real_path, request)

        if request.permissions is not None:
            self._apply_permissions(real_path, request.permissions)

        return self._metadata_service.build_metadata(
            real_path, follow_link=follow_link
        )

    def copy_entry(
        self,
        source_virtual: str,
        destination_virtual: str,
        overwrite: bool = False,
    ) -> FileSystemEntryMetadata:
        """复制文件或递归复制文件夹。

        Args:
            source_virtual: 源沙箱虚拟路径。
            destination_virtual: 目标沙箱虚拟路径。
            overwrite: 目标已存在时是否覆盖。

        Returns:
            副本的元数据。

        Raises:
            BusinessError: 源不存在、目标存在且不允许覆盖或复制失败。
        """
        source_real = self._path_service.resolve_real_path(
            source_virtual, follow_link=True
        )
        if not source_real.exists():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"源路径不存在：{source_virtual}",
            )

        destination_real = self._path_service.resolve_real_path(
            destination_virtual, follow_link=False
        )
        self._path_service.ensure_parent_exists(destination_real)

        if destination_real.exists() or destination_real.is_symlink():
            if not overwrite:
                raise BusinessError(
                    ErrorCode.FILE_EXISTS,
                    f"目标已存在：{destination_real.name}",
                )
            self._remove_existing_target(destination_real)

        try:
            if source_real.is_dir():
                shutil.copytree(source_real, destination_real, symlinks=True)
            else:
                shutil.copy2(source_real, destination_real)
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"复制失败：{source_virtual}",
            ) from exc

        return self._metadata_service.build_metadata(
            destination_real, follow_link=True
        )

    def _compute_renamed_path(
        self,
        real_path: Path,
        request: UpdateMetadataRequest,
    ) -> Optional[Path]:
        """根据请求计算重命名 / 移动后的真实路径。

        当同时提供 ``path`` 与 ``name`` 时，``name`` 被忽略。

        Args:
            real_path: 当前真实路径。
            request: 修改请求。

        Returns:
            新真实路径；未要求重命名时返回 ``None``。
        """
        if request.path is not None:
            return self._path_service.resolve_real_path(
                request.path, follow_link=False
            )
        if request.name is not None:
            parent_virtual = self._path_service.to_virtual_path(real_path.parent)
            new_virtual = (
                f"/{request.name}"
                if parent_virtual == "/"
                else f"{parent_virtual}/{request.name}"
            )
            return self._path_service.resolve_real_path(
                new_virtual, follow_link=False
            )
        return None

    def _rename_entry(self, real_path: Path, new_real_path: Path) -> None:
        """将真实路径重命名 / 移动到新的真实路径。"""
        if new_real_path.exists() or new_real_path.is_symlink():
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标已存在：{new_real_path.name}",
            )
        try:
            real_path.rename(new_real_path)
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"重命名失败：{real_path.name}",
            ) from exc

    def _apply_hidden_attribute(
        self,
        real_path: Path,
        is_hidden: bool,
    ) -> Path:
        """按需切换前导点以修改隐藏属性。"""
        current_hidden = real_path.name.startswith(".")
        if is_hidden == current_hidden:
            return real_path
        new_name = "." + real_path.name if is_hidden else real_path.name[1:]
        new_path = real_path.parent / new_name
        if new_path.exists() or new_path.is_symlink():
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标已存在：{new_name}",
            )
        try:
            real_path.rename(new_path)
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"隐藏属性修改失败：{real_path.name}",
            ) from exc
        return new_path

    def _apply_times(
        self,
        real_path: Path,
        request: UpdateMetadataRequest,
    ) -> None:
        """按需修改访问时间与修改时间。"""
        current_stat = real_path.stat()
        atime = (
            request.accessed_at
            if request.accessed_at is not None
            else current_stat.st_atime
        )
        mtime = (
            request.modified_at
            if request.modified_at is not None
            else current_stat.st_mtime
        )
        try:
            os.utime(real_path, (atime, mtime))
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"修改时间失败：{real_path.name}",
            ) from exc

    def _apply_permissions(self, real_path: Path, permissions: str) -> None:
        """按需修改权限。"""
        mode = parse_permissions_string(permissions)
        try:
            os.chmod(real_path, mode)
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"修改权限失败：{real_path.name}",
            ) from exc

    def _remove_existing_target(self, target_path: Path) -> None:
        """覆盖前删除已存在的目标。"""
        if target_path.is_symlink() or target_path.is_file():
            target_path.unlink()
        elif target_path.is_dir():
            shutil.rmtree(target_path)


__all__ = ["ModifyService"]
