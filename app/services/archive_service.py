"""压缩打包下载服务。

本模块提供 :class:`ArchiveService`，负责将多个沙箱路径解析为一组
归档条目，并流式生成 ZIP 内容。目录输入会被递归展开为其中的所有
文件；ZIP 内的相对路径保留输入的目录结构，以避免同名文件冲突。

归档构建时先写入 :class:`tempfile.SpooledTemporaryFile`，小包留在
内存、大包自动溢出到磁盘；随后按块读取并交给流式响应，保证内存
占用与归档大小解耦。
"""

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Iterator

from app.errors import BusinessError, ErrorCode
from app.services.path_service import PathService


MAX_ARCHIVE_MEMORY_BUFFER: int = 10 * 1024 * 1024
"""归档构建时的内存缓冲上限（字节），超过后自动溢出到磁盘。"""

ARCHIVE_STREAM_CHUNK_SIZE: int = 16 * 1024 * 1024
"""输出 ZIP 流时每次读取的块大小（字节）。"""


@dataclass(frozen=True)
class ArchiveEntry:
    """归档条目。

    Attributes:
        real_path: 文件或符号链接的真实路径。
        archive_name: 在 ZIP 内的相对路径，使用正斜杠。
    """

    real_path: Path
    archive_name: str


class ArchiveService:
    """压缩打包下载服务。

    Attributes:
        path_service: 沙箱路径解析服务。
    """

    def __init__(self, path_service: PathService) -> None:
        """构造归档服务。

        Args:
            path_service: 沙箱路径解析服务。
        """
        self._path_service: PathService = path_service

    def prepare_entries(
        self,
        virtual_paths: list[str],
        follow_link: bool = True,
    ) -> list[ArchiveEntry]:
        """解析输入路径并收集所有要打包的条目。

        Args:
            virtual_paths: 要打包的沙箱虚拟路径列表。
            follow_link: 是否跟随符号链接。

        Returns:
            归档条目列表，顺序与输入一致。

        Raises:
            BusinessError: 路径列表为空、路径非法或目标不存在。
        """
        if not virtual_paths:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                "paths 不能为空",
            )

        entries: list[ArchiveEntry] = []
        for virtual_path in virtual_paths:
            entries.extend(
                self._collect_from_path(virtual_path, follow_link)
            )
        return entries

    def _collect_from_path(
        self,
        virtual_path: str,
        follow_link: bool,
    ) -> list[ArchiveEntry]:
        """从单个输入路径收集归档条目。

        归档名取自输入虚拟路径（去除前导斜杠），而非解析后的真实
        路径。这样即使输入是符号链接、且 ``follow_link=True``，ZIP
        内的名称仍然是用户请求的名字，而非链接目标的路径。

        Args:
            virtual_path: 沙箱虚拟路径。
            follow_link: 是否跟随符号链接。

        Returns:
            该路径对应的归档条目列表。

        Raises:
            BusinessError: 路径非法、不存在或指向沙箱根目录。
        """
        normalized = self._path_service.normalize(virtual_path)
        real_path = self._path_service.resolve_real_path(
            virtual_path, follow_link=follow_link
        )
        if not real_path.exists() and not real_path.is_symlink():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"路径不存在：{virtual_path}",
            )

        base_name = normalized.lstrip("/")
        if base_name == "":
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                "不能直接打包沙箱根目录，请选择具体的文件或子目录",
            )

        if real_path.is_dir():
            return self._collect_directory(real_path, base_name, follow_link)
        return [ArchiveEntry(real_path=real_path, archive_name=base_name)]

    def _collect_directory(
        self,
        directory: Path,
        base_name: str,
        follow_link: bool,
    ) -> list[ArchiveEntry]:
        """递归收集目录下的所有文件。

        Args:
            directory: 目录的真实路径。
            base_name: 该目录在 ZIP 内的顶层名称。
            follow_link: 是否跟随符号链接。

        Returns:
            归档条目列表。空目录会返回空列表。
        """
        entries: list[ArchiveEntry] = []
        for current_dir, _, filenames in os.walk(
            directory, followlinks=follow_link
        ):
            current_path = Path(current_dir)
            relative_directory = current_path.relative_to(directory)
            for filename in filenames:
                file_path = current_path / filename
                archive_name = build_archive_name(
                    base_name, relative_directory, filename
                )
                entries.append(
                    ArchiveEntry(
                        real_path=file_path,
                        archive_name=archive_name,
                    )
                )
        return entries


def build_archive_name(
    base_name: str,
    relative_directory: Path,
    filename: str,
) -> str:
    """构造 ZIP 内的相对路径名。

    Args:
        base_name: ZIP 内的顶层名称。
        relative_directory: 相对输入目录的子目录路径。
        filename: 文件名。

    Returns:
        使用正斜杠分隔的 ZIP 内相对路径。
    """
    parts: list[str] = [base_name]
    relative_string = str(relative_directory).replace("\\", "/")
    if relative_string not in ("", "."):
        parts.append(relative_string)
    parts.append(filename)
    return "/".join(parts)


def iter_archive_stream(entries: list[ArchiveEntry]) -> Iterator[bytes]:
    """将归档条目流式打包为 ZIP 字节流。

    先写入 :class:`tempfile.SpooledTemporaryFile`，随后按块读取并
    产出。调用方应在响应结束后确保生成器被完整消费或被关闭，
    以便临时文件被清理。

    Args:
        entries: 归档条目列表。

    Yields:
        ZIP 格式的字节块。
    """
    with SpooledTemporaryFile(
        max_size=MAX_ARCHIVE_MEMORY_BUFFER, suffix=".zip"
    ) as spool:
        with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in entries:
                archive.write(entry.real_path, entry.archive_name)
        spool.seek(0)
        while True:
            chunk = spool.read(ARCHIVE_STREAM_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk


__all__ = [
    "ArchiveEntry",
    "ArchiveService",
    "build_archive_name",
    "iter_archive_stream",
    "MAX_ARCHIVE_MEMORY_BUFFER",
    "ARCHIVE_STREAM_CHUNK_SIZE",
]
