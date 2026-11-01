"""压缩打包下载服务。

本模块提供 :class:`ArchiveService`，负责将多个沙箱路径解析为一组
归档条目，并流式生成 ZIP 内容。目录输入会被递归展开为其中的所有
文件；ZIP 内的相对路径以所有选中路径的最深公共目录为根，避免把
沙箱根目录到目标的整条路径都写入归档。

归档构建时先写入 :class:`tempfile.SpooledTemporaryFile`，小包留在
内存、大包自动溢出到磁盘；随后按块读取并交给流式响应，保证内存
占用与归档大小解耦。
"""

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import SpooledTemporaryFile
from typing import Iterator

from ..errors import BusinessError, ErrorCode
from .path_service import PathService


MAX_ARCHIVE_MEMORY_BUFFER: int = 10 * 1024 * 1024
"""归档构建时的内存缓冲上限（字节），超过后自动溢出到磁盘。"""

ARCHIVE_STREAM_CHUNK_SIZE: int = 16 * 1024 * 1024
"""输出 ZIP 流时每次读取的块大小（字节）。"""

DEFAULT_ARCHIVE_FILENAME: str = "archive.zip"
"""没有共同父目录时使用的默认下载文件名。"""


@dataclass(frozen=True)
class ArchiveEntry:
    """归档条目。

    Attributes:
        real_path: 文件或符号链接的真实路径。
        archive_name: 在 ZIP 内的相对路径，使用正斜杠。
    """

    real_path: Path
    archive_name: str


@dataclass(frozen=True)
class ArchiveSource:
    """已解析的归档输入路径。

    Attributes:
        virtual_path: 规范化后的沙箱虚拟路径。
        real_path: 解析后的真实路径。
        is_directory: 输入是否为目录。
        common_directory: 用于计算公共父目录的虚拟路径：目录取自身，
            文件取所在目录。
    """

    virtual_path: str
    real_path: Path
    is_directory: bool
    common_directory: str


@dataclass(frozen=True)
class ArchivePlan:
    """一次压缩下载的完整构建计划。

    Attributes:
        entries: ZIP 内的所有条目。
        root_name: ZIP 最外层目录名；为空表示直接以沙箱根目录为根，
            不额外创建外层目录。
    """

    entries: list[ArchiveEntry]
    root_name: str

    @property
    def filename(self) -> str:
        """返回下载时使用的 ZIP 文件名。"""
        if self.root_name:
            return f"{self.root_name}.zip"
        return DEFAULT_ARCHIVE_FILENAME


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
        return self.prepare_archive(virtual_paths, follow_link).entries

    def prepare_archive(
        self,
        virtual_paths: list[str],
        follow_link: bool = True,
    ) -> ArchivePlan:
        """解析输入路径并构建完整的压缩下载计划。

        ZIP 内的路径以所有输入路径的最深公共目录为根：公共目录的
        名字作为最外层目录，其余路径相对该目录保留。公共目录为沙箱
        根目录时不额外创建外层目录。

        Args:
            virtual_paths: 要打包的沙箱虚拟路径列表。
            follow_link: 是否跟随符号链接。

        Returns:
            归档条目与最外层目录名。

        Raises:
            BusinessError: 路径列表为空、路径非法或目标不存在。
        """
        if not virtual_paths:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                "paths 不能为空",
            )

        sources = [
            self._resolve_source(virtual_path, follow_link)
            for virtual_path in virtual_paths
        ]
        common_directory = find_common_directory(
            [source.common_directory for source in sources]
        )
        root_name = (
            ""
            if common_directory == "/"
            else PurePosixPath(common_directory).name
        )

        entries: list[ArchiveEntry] = []
        for source in sources:
            entries.extend(
                self._collect_from_source(
                    source, common_directory, root_name, follow_link
                )
            )
        return ArchivePlan(entries=entries, root_name=root_name)

    def _resolve_source(
        self,
        virtual_path: str,
        follow_link: bool,
    ) -> ArchiveSource:
        """解析单个输入路径并校验其存在性。

        Args:
            virtual_path: 沙箱虚拟路径。
            follow_link: 是否跟随符号链接。

        Returns:
            解析后的归档输入。

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

        if normalized == "/":
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                "不能直接打包沙箱根目录，请选择具体的文件或子目录",
            )

        is_directory = real_path.is_dir()
        common_directory = (
            normalized if is_directory else virtual_parent(normalized)
        )
        return ArchiveSource(
            virtual_path=normalized,
            real_path=real_path,
            is_directory=is_directory,
            common_directory=common_directory,
        )

    def _collect_from_source(
        self,
        source: ArchiveSource,
        common_directory: str,
        root_name: str,
        follow_link: bool,
    ) -> list[ArchiveEntry]:
        """从单个已解析输入收集归档条目。

        归档名取自输入虚拟路径，而非解析后的真实路径。这样即使输入
        是符号链接、且 ``follow_link=True``，ZIP 内的名称仍然是用户
        请求的名字，而非链接目标的路径。

        Args:
            source: 已解析的输入路径。
            common_directory: 所有输入的公共父目录。
            root_name: ZIP 最外层目录名，空字符串表示不添加外层目录。
            follow_link: 是否跟随符号链接。

        Returns:
            该路径对应的归档条目列表。
        """
        relative_name = relative_archive_path(
            source.virtual_path, common_directory
        )
        base_name = join_archive_name(root_name, relative_name)

        if source.is_directory:
            return self._collect_directory(
                source.real_path, base_name, follow_link
            )
        return [
            ArchiveEntry(
                real_path=source.real_path,
                archive_name=base_name,
            )
        ]

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


def virtual_parent(virtual_path: str) -> str:
    """返回虚拟路径的父目录。

    Args:
        virtual_path: 规范化后的沙箱虚拟路径。

    Returns:
        父目录的虚拟路径；根目录的父目录仍为根目录。
    """
    parent = str(PurePosixPath(virtual_path).parent)
    return "/" if parent == "." else parent


def find_common_directory(directories: list[str]) -> str:
    """求一组虚拟目录路径的最深公共目录。

    Args:
        directories: 非空的虚拟目录路径列表。

    Returns:
        最深公共目录的虚拟路径；无更深公共目录时返回 ``/``。
    """
    common_parts = PurePosixPath(directories[0]).parts
    for directory in directories[1:]:
        parts = PurePosixPath(directory).parts
        limit = min(len(common_parts), len(parts))
        index = 0
        while index < limit and common_parts[index] == parts[index]:
            index += 1
        common_parts = common_parts[:index]

    if len(common_parts) <= 1:
        return "/"
    return "/" + "/".join(common_parts[1:])


def relative_archive_path(virtual_path: str, directory: str) -> str:
    """计算虚拟路径相对指定目录的路径。

    Args:
        virtual_path: 对象自身的虚拟路径。
        directory: 作为基准的公共目录虚拟路径。

    Returns:
        使用正斜杠分隔的相对路径；与目录相同时返回空字符串。
    """
    relative = PurePosixPath(virtual_path).relative_to(
        PurePosixPath(directory)
    )
    relative_string = relative.as_posix()
    return "" if relative_string == "." else relative_string


def join_archive_name(prefix: str, relative_name: str) -> str:
    """拼接 ZIP 内路径的各个非空部分。

    Args:
        prefix: 外层目录名，可为空。
        relative_name: 相对路径，可为空。

    Returns:
        使用正斜杠分隔的 ZIP 内相对路径。
    """
    return "/".join(part for part in (prefix, relative_name) if part)


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
    "ArchivePlan",
    "ArchiveService",
    "ArchiveSource",
    "build_archive_name",
    "find_common_directory",
    "iter_archive_stream",
    "join_archive_name",
    "relative_archive_path",
    "virtual_parent",
    "DEFAULT_ARCHIVE_FILENAME",
    "MAX_ARCHIVE_MEMORY_BUFFER",
    "ARCHIVE_STREAM_CHUNK_SIZE",
]
