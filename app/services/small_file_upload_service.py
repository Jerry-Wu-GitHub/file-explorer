"""小文件上传服务。

本模块提供 :class:`SmallFileUploadService`，负责处理
``multipart/form-data`` 形式的单文件上传。上传过程采用「写入同
目录临时文件 → fsync → 原子重命名」的策略，保证目标文件在写入
完成后才对外可见，避免读到半写文件。
"""

import os
import uuid
from pathlib import Path
from typing import BinaryIO

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.schemas.filesystem import FileSystemEntryMetadata
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService


UPLOAD_READ_CHUNK_SIZE: int = 1024 * 1024
"""从上传流读取内容时的块大小（字节）。"""

UPLOAD_TEMP_SUFFIX: str = ".uploading"
"""上传过程中临时文件的后缀。"""


def sanitize_upload_filename(filename: str | None) -> str:
    """从客户端提供的文件名中提取安全的文件名。

    客户端可能提供含路径分隔符的文件名（例如 ``a/b/c.txt`` 或
    ``a\\b\\c.txt``），本函数只取最后一段，并拒绝空名、``.``、
    ``..`` 与含空字节的名称。

    Args:
        filename: 客户端提供的原始文件名，可为 ``None``。

    Returns:
        去除路径成分后的安全文件名。

    Raises:
        BusinessError: 文件名为空、非法或包含空字节。
    """
    if filename is None or filename.strip() == "":
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            "文件名不能为空",
        )
    normalized = filename.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].strip()
    if name == "" or name in (".", ".."):
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"文件名无效：{filename!r}",
        )
    if "\0" in name:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            "文件名包含空字节",
        )
    return name


class SmallFileUploadService:
    """小文件上传服务。

    Attributes:
        path_service: 沙箱路径解析服务。
        metadata_service: 元数据组装服务。
        config: 项目全局配置，用于读取上传大小上限。
    """

    def __init__(
        self,
        path_service: PathService,
        metadata_service: MetadataService,
        config: Config,
    ) -> None:
        """构造小文件上传服务。

        Args:
            path_service: 沙箱路径解析服务。
            metadata_service: 元数据组装服务。
            config: 项目全局配置。
        """
        self._path_service: PathService = path_service
        self._metadata_service: MetadataService = metadata_service
        self._config: Config = config

    def upload_file(
        self,
        target_directory_virtual: str,
        filename: str | None,
        content: BinaryIO,
        overwrite: bool = False,
    ) -> FileSystemEntryMetadata:
        """将上传内容写入目标目录。

        Args:
            target_directory_virtual: 目标目录的沙箱虚拟路径。
            filename: 客户端提供的文件名，仅取最后一段作为最终文件名。
            content: 上传内容流，需支持 ``read`` 方法。
            overwrite: 目标已存在时是否覆盖。

        Returns:
            上传完成后的文件元数据。

        Raises:
            BusinessError: 文件名非法、目录不存在、目标冲突、大小超限
                或写入失败。
        """
        sanitized_name = sanitize_upload_filename(filename)
        directory_real = self._resolve_target_directory(
            target_directory_virtual
        )
        target_real = directory_real / sanitized_name

        self._check_target_conflicts(target_real, overwrite)

        temp_path = self._create_temp_path(directory_real, sanitized_name)
        try:
            self._stream_to_file(content, temp_path)
            os.replace(temp_path, target_real)
        except BusinessError:
            self._safe_unlink(temp_path)
            raise
        except OSError as exc:
            self._safe_unlink(temp_path)
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"保存文件失败：{sanitized_name}",
            ) from exc

        return self._metadata_service.build_metadata(
            target_real, follow_link=True
        )

    def _resolve_target_directory(self, virtual_path: str) -> Path:
        """解析目标目录真实路径并校验其存在且为目录。

        Args:
            virtual_path: 目标目录的沙箱虚拟路径。

        Returns:
            目标目录的真实路径。

        Raises:
            BusinessError: 路径非法、不存在或不是目录。
        """
        real_path = self._path_service.resolve_real_path(
            virtual_path, follow_link=True
        )
        if not real_path.exists():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"目标目录不存在：{virtual_path}",
            )
        if not real_path.is_dir():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"目标不是目录：{virtual_path}",
            )
        return real_path

    def _check_target_conflicts(
        self,
        target_real: Path,
        overwrite: bool,
    ) -> None:
        """校验目标路径是否允许写入。

        Args:
            target_real: 目标文件真实路径。
            overwrite: 目标已存在时是否覆盖。

        Raises:
            BusinessError: 目标为已存在的目录，或已存在且不允许覆盖。
        """
        if target_real.is_dir():
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标已存在且为目录：{target_real.name}",
            )
        if (target_real.exists() or target_real.is_symlink()) and not overwrite:
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"文件已存在：{target_real.name}",
            )

    def _create_temp_path(
        self,
        directory: Path,
        base_name: str,
    ) -> Path:
        """构造与目标同目录的唯一临时文件路径。

        使用同目录可保证 :func:`os.replace` 的原子性；使用随机后缀
        避免并发上传同名文件时冲突。

        Args:
            directory: 目标目录真实路径。
            base_name: 目标文件名，用于临时文件前缀。

        Returns:
            临时文件路径。
        """
        token = uuid.uuid4().hex
        return directory / f".{base_name}.{token}{UPLOAD_TEMP_SUFFIX}"

    def _stream_to_file(self, content: BinaryIO, temp_path: Path) -> None:
        """将上传流写入临时文件并落盘。

        写入过程中累计字节数，超过配置的上限时抛出
        ``PAYLOAD_TOO_LARGE``，避免将超大文件写入磁盘。

        Args:
            content: 上传内容流。
            temp_path: 临时文件路径。

        Raises:
            BusinessError: 文件大小超过配置上限。
        """
        total = 0
        with temp_path.open("wb") as output:
            while True:
                chunk = content.read(UPLOAD_READ_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > self._config.max_upload_size:
                    raise BusinessError(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        f"文件大小超过限制：{self._config.max_upload_size} 字节",
                    )
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())

    def _safe_unlink(self, path: Path) -> None:
        """尽力删除临时文件，忽略所有异常。"""
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


__all__ = ["SmallFileUploadService", "sanitize_upload_filename"]
