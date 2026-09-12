"""分片文件的写入与读取。"""

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import Iterator, Optional

from app.utils.errors import ChecksumMismatchError, InsufficientStorageError
from app.utils.uploads import session_store


def write_chunk(upload_id: str, chunk_number: int, content: bytes) -> None:
    """原子写入分片：先写临时文件并 fsync，再重命名，避免半写分片。"""
    target_path: Path = session_store.chunk_file_path(upload_id, chunk_number)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    _check_disk_space(target_path.parent, len(content))

    temp_path: Path = target_path.with_name(
        f"{target_path.name}.{uuid.uuid4().hex}.tmp"
    )
    with open(temp_path, "wb") as file_handle:
        file_handle.write(content)
        file_handle.flush()
        os.fsync(file_handle.fileno())
    os.replace(temp_path, target_path)


def verify_chunk_checksum(
    content: bytes,
    content_md5: Optional[str],
    chunk_sha256: Optional[str],
) -> None:
    """校验分片校验值，不匹配时抛出 422 且不得保存。"""
    if content_md5 is not None:
        actual_md5: str = hashlib.md5(content).hexdigest()
        if actual_md5 != content_md5.lower():
            raise ChecksumMismatchError("分片 MD5 校验失败")
    if chunk_sha256 is not None:
        actual_sha256: str = hashlib.sha256(content).hexdigest()
        if actual_sha256 != chunk_sha256.lower():
            raise ChecksumMismatchError("分片 SHA-256 校验失败")


def iter_chunk_paths(upload_id: str, total_chunks: int) -> Iterator[Path]:
    """按编号升序产出分片文件路径。"""
    for chunk_number in range(total_chunks):
        yield session_store.chunk_file_path(upload_id, chunk_number)


def _check_disk_space(directory: Path, required_bytes: int) -> None:
    """检查目录所在文件系统剩余空间是否足够。"""
    disk_usage = shutil.disk_usage(str(directory))
    if disk_usage.free < required_bytes:
        raise InsufficientStorageError("磁盘剩余空间不足，无法写入分片")
