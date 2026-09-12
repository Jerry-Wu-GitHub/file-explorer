"""分片文件存储。

本模块提供 :class:`LocalUploadChunkStorage`，负责在本地文件系统上
写入、查询、合并与清理分片。分片写入与合并均采用「写临时文件 →
fsync → 原子重命名」的策略，避免读到半写文件。

存储根目录与沙箱根目录完全分离，不可通过任何对外接口访问。
"""

from contextlib import contextmanager
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

from ..constants import (
    CHUNK_FILE_SUFFIX,
    CHUNK_TEMP_SUFFIX,
    MERGE_TEMP_SUFFIX,
)
from ..errors import BusinessError, ErrorCode


CHUNK_IO_BUFFER_SIZE: int = 1024 * 1024
"""分片读写时的块大小（字节）。"""


class LocalUploadChunkStorage:
    """本地文件系统上的分片存储。

    目录布局：

    - ``{temp_root}/{upload_id}/chunks/{chunk_number}.part``：分片文件；
    - ``{temp_root}/{upload_id}/chunks/{chunk_number}.part.tmp``：
      写入过程中的临时文件，成功后原子重命名为分片文件。

    Attributes:
        temp_root: 分片临时根目录的绝对路径。
    """

    def __init__(self, temp_root: Path) -> None:
        """构造分片存储。

        Args:
            temp_root: 分片临时根目录。
        """
        self._temp_root: Path = Path(temp_root).resolve()
        self._temp_root.mkdir(parents=True, exist_ok=True)

    @property
    def temp_root(self) -> Path:
        """返回分片临时根目录。

        Returns:
            临时根目录绝对路径。
        """
        return self._temp_root

    def session_root(self, upload_id: str) -> Path:
        """返回某个上传会话的根目录。

        Args:
            upload_id: 上传会话 ID。

        Returns:
            该会话的根目录。
        """
        return self._temp_root / upload_id

    def chunks_directory(self, upload_id: str) -> Path:
        """返回某个上传会话的分片目录。

        Args:
            upload_id: 上传会话 ID。

        Returns:
            该会话的分片目录。
        """
        return self.session_root(upload_id) / "chunks"

    def chunk_path(self, upload_id: str, chunk_number: int) -> Path:
        """返回某个分片文件的最终路径。

        Args:
            upload_id: 上传会话 ID。
            chunk_number: 分片编号。

        Returns:
            分片文件路径。
        """
        name = f"{chunk_number}{CHUNK_FILE_SUFFIX}"
        return self.chunks_directory(upload_id) / name

    def ensure_session_directory(self, upload_id: str) -> None:
        """确保会话的分片目录存在。

        Args:
            upload_id: 上传会话 ID。
        """
        self.chunks_directory(upload_id).mkdir(parents=True, exist_ok=True)

    def write_chunk(
        self,
        upload_id: str,
        chunk_number: int,
        content: BinaryIO,
        expected_size: int,
    ) -> int:
        """将分片内容原子地写入存储。

        写入时先写临时文件并 fsync，成功后原子重命名为最终文件名；
        若实际写入字节数与 ``expected_size`` 不符，则丢弃临时文件
        并抛出 ``INVALID_CHUNK_SIZE``。

        Args:
            upload_id: 上传会话 ID。
            chunk_number: 分片编号。
            content: 分片内容流，需支持 ``read`` 方法。
            expected_size: 期望的字节数。

        Returns:
            实际写入的字节数。

        Raises:
            BusinessError: 写入字节数与期望不符，或写入失败。
        """
        self.ensure_session_directory(upload_id)
        final_path = self.chunk_path(upload_id, chunk_number)
        temp_path = self.chunks_directory(upload_id) / (
            f"{chunk_number}{CHUNK_TEMP_SUFFIX}"
        )
        written = 0
        try:
            with temp_path.open("wb") as output:
                written = self._stream_content(content, output)
                output.flush()
                os.fsync(output.fileno())
            if written != expected_size:
                raise BusinessError(
                    ErrorCode.INVALID_CHUNK_SIZE,
                    f"分片 {chunk_number} 实际写入 {written} 字节，"
                    f"预期 {expected_size} 字节",
                )
            os.replace(temp_path, final_path)
        except BusinessError:
            self._safe_unlink(temp_path)
            raise
        except OSError as exc:
            self._safe_unlink(temp_path)
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"写入分片失败：{upload_id}/{chunk_number}",
            ) from exc
        return written

    def chunk_size_on_disk(
        self,
        upload_id: str,
        chunk_number: int,
    ) -> Optional[int]:
        """读取某个分片文件当前的大小。

        Args:
            upload_id: 上传会话 ID。
            chunk_number: 分片编号。

        Returns:
            分片字节数；分片不存在时返回 ``None``。
        """
        path = self.chunk_path(upload_id, chunk_number)
        if not path.is_file():
            return None
        return path.stat().st_size

    def list_uploaded_chunks(self, upload_id: str) -> list[int]:
        """列出会话已上传的分片编号。

        仅统计符合 ``{chunk_number}.part`` 命名的文件，忽略临时文件。

        Args:
            upload_id: 上传会话 ID。

        Returns:
            分片编号列表，升序。
        """
        directory = self.chunks_directory(upload_id)
        if not directory.is_dir():
            return []
        numbers: list[int] = []
        suffix_length = len(CHUNK_FILE_SUFFIX)
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            name = entry.name
            if not name.endswith(CHUNK_FILE_SUFFIX):
                continue
            number_part = name[:-suffix_length]
            if not number_part.isdigit():
                continue
            numbers.append(int(number_part))
        numbers.sort()
        return numbers

    def remove_chunk(self, upload_id: str, chunk_number: int) -> None:
        """删除指定分片。分片不存在时静默返回。

        Args:
            upload_id: 上传会话 ID。
            chunk_number: 分片编号。
        """
        self._safe_unlink(self.chunk_path(upload_id, chunk_number))

    def merge_chunks(
        self,
        upload_id: str,
        total_chunks: int,
        target_path: Path,
    ) -> None:
        """按分片编号升序合并到目标文件。

        合并写入目标目录下的临时文件，fsync 后通过 ``os.replace``
        原子替换目标文件。任一分片缺失或写入失败时，临时文件会被
        清理，目标文件保持不变。

        Args:
            upload_id: 上传会话 ID。
            total_chunks: 分片总数；为 0 时生成空文件。
            target_path: 目标文件的真实路径。

        Raises:
            BusinessError: 分片缺失或合并失败。
        """
        target_parent = target_path.parent
        target_parent.mkdir(parents=True, exist_ok=True)
        temp_name = (
            f".{target_path.name}.{uuid.uuid4().hex}{MERGE_TEMP_SUFFIX}"
        )
        temp_path = target_parent / temp_name
        try:
            with temp_path.open("wb") as output:
                for chunk_number in range(total_chunks):
                    chunk_path = self.chunk_path(upload_id, chunk_number)
                    if not chunk_path.is_file():
                        raise BusinessError(
                            ErrorCode.UPLOAD_INCOMPLETE,
                            f"分片 {chunk_number} 不存在",
                        )
                    self._copy_chunk_into(chunk_path, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_path, target_path)
        except BusinessError:
            self._safe_unlink(temp_path)
            raise
        except OSError as exc:
            self._safe_unlink(temp_path)
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"合并分片失败：{upload_id}",
            ) from exc

    def cleanup_session(self, upload_id: str) -> None:
        """递归删除会话的所有临时文件。

        Args:
            upload_id: 上传会话 ID。
        """
        shutil.rmtree(self.session_root(upload_id), ignore_errors=True)

    def available_disk_space_bytes(self) -> int:
        """返回临时根目录所在文件系统的剩余可用空间。

        Returns:
            剩余字节数。
        """
        return shutil.disk_usage(self._temp_root).free

    def _stream_content(
        self,
        content: BinaryIO,
        output: BinaryIO,
    ) -> int:
        """将内容流写入输出文件并返回累计字节数。

        Args:
            content: 输入流。
            output: 输出流。

        Returns:
            写入的总字节数。
        """
        total = 0
        while True:
            buffer = content.read(CHUNK_IO_BUFFER_SIZE)
            if not buffer:
                break
            output.write(buffer)
            total += len(buffer)
        return total

    def _copy_chunk_into(self, source: Path, output: BinaryIO) -> None:
        """将分片文件内容追加到输出流。

        Args:
            source: 分片文件路径。
            output: 输出流。
        """
        with source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output, CHUNK_IO_BUFFER_SIZE)

    def _safe_unlink(self, path: Path) -> None:
        """尽力删除文件，忽略所有异常。"""
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


    @contextmanager
    def staged_merge(
        self,
        upload_id: str,
        total_chunks: int,
        target_path: Path,
    ) -> Iterator[Path]:
        """将分片合并到目标目录下的临时文件，并 yield 其路径。

        允许调用方在 ``with`` 块内对临时文件执行校验（例如整体
        checksum）。若正常退出，临时文件通过 ``os.replace`` 原子
        重命名为目标文件；若抛出异常，临时文件被清理，目标文件
        保持不变。

        Args:
            upload_id: 上传会话 ID。
            total_chunks: 分片总数；为 0 时生成空文件。
            target_path: 目标文件的真实路径。

        Yields:
            合并后的临时文件路径。

        Raises:
            BusinessError: 分片缺失或合并失败。
        """
        target_parent = target_path.parent
        target_parent.mkdir(parents=True, exist_ok=True)
        temp_name = (
            f".{target_path.name}.{uuid.uuid4().hex}{MERGE_TEMP_SUFFIX}"
        )
        temp_path = target_parent / temp_name
        try:
            with temp_path.open("wb") as output:
                for chunk_number in range(total_chunks):
                    chunk_path = self.chunk_path(upload_id, chunk_number)
                    if not chunk_path.is_file():
                        raise BusinessError(
                            ErrorCode.UPLOAD_INCOMPLETE,
                            f"分片 {chunk_number} 不存在",
                        )
                    self._copy_chunk_into(chunk_path, output)
                output.flush()
                os.fsync(output.fileno())
            yield temp_path
            os.replace(temp_path, target_path)
        except OSError as exc:
            self._safe_unlink(temp_path)
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"合并分片失败：{upload_id}",
            ) from exc
        except Exception:
            self._safe_unlink(temp_path)
            raise


__all__ = ["LocalUploadChunkStorage", "CHUNK_IO_BUFFER_SIZE"]
