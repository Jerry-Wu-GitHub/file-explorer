"""上传会话与分片文件的存储层。

会话元数据持久化为 JSON 文件、分片持久化为独立文件，天然支持
多 worker（多进程）共享；通过 flock 文件锁保证并发一致性。
"""

import fcntl
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Iterator, Optional

from app.config import get_config
from app.models.upload_session import UploadSession
from app.utils.errors import UploadNotFoundError


def ensure_upload_dirs() -> tuple[Path, Path]:
    """确保上传临时目录结构存在，返回（会话目录, 分片根目录）。"""
    upload_root: Path = Path(get_config().upload_temp_root)
    session_dir: Path = upload_root / "sessions"
    chunk_root: Path = upload_root / "chunks"
    session_dir.mkdir(parents=True, exist_ok=True)
    chunk_root.mkdir(parents=True, exist_ok=True)
    return session_dir, chunk_root


def upload_root_path() -> Path:
    """返回上传临时根目录。"""
    return Path(get_config().upload_temp_root)


def session_file_path(upload_id: str) -> Path:
    """返回会话元数据文件路径。"""
    session_dir, _ = ensure_upload_dirs()
    return session_dir / f"{upload_id}.json"


def lock_file_path(upload_id: str) -> Path:
    """返回会话锁文件路径。"""
    session_dir, _ = ensure_upload_dirs()
    return session_dir / f"{upload_id}.lock"


def chunk_dir_path(upload_id: str) -> Path:
    """返回分片目录路径。"""
    _, chunk_root = ensure_upload_dirs()
    return chunk_root / upload_id


def chunk_file_path(upload_id: str, chunk_number: int) -> Path:
    """返回指定分片文件路径。"""
    return chunk_dir_path(upload_id) / f"{chunk_number}.part"


class SessionLock:
    """基于 flock 的会话互斥锁（阻塞式），保证并发修改原子化。"""

    def __init__(self, upload_id: str) -> None:
        self._lock_path: Path = lock_file_path(upload_id)
        self._file_handle = None

    def __enter__(self) -> "SessionLock":
        self._file_handle = open(self._lock_path, "a+")
        fcntl.flock(self._file_handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._file_handle is not None:
            fcntl.flock(self._file_handle, fcntl.LOCK_UN)
            self._file_handle.close()
            self._file_handle = None


def save_session(session: UploadSession) -> None:
    """原子化持久化会话元数据（临时文件 + 重命名）。"""
    session_path: Path = session_file_path(session.upload_id)
    temp_path: Path = session_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    payload: str = session.model_dump_json()
    with open(temp_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(payload)
        file_handle.flush()
        os.fsync(file_handle.fileno())
    os.replace(temp_path, session_path)


def load_session(upload_id: str) -> UploadSession:
    """读取会话元数据，不存在时抛出 404。"""
    session_path: Path = session_file_path(upload_id)
    if not session_path.exists():
        raise UploadNotFoundError(f"上传会话不存在: {upload_id}")
    try:
        with open(session_path, "r", encoding="utf-8") as file_handle:
            raw_data: dict = json.load(file_handle)
    except (json.JSONDecodeError, OSError) as exc:
        raise UploadNotFoundError(f"上传会话数据损坏: {upload_id}") from exc
    return UploadSession.model_validate(raw_data)


def delete_session_file(upload_id: str) -> None:
    """删除会话元数据文件。"""
    session_file_path(upload_id).unlink(missing_ok=True)
    lock_file_path(upload_id).unlink(missing_ok=True)


def list_session_ids() -> Iterator[str]:
    """列出全部会话 ID。"""
    session_dir, _ = ensure_upload_dirs()
    for file_path in sorted(session_dir.glob("*.json")):
        yield file_path.stem


def delete_chunk_dir(upload_id: str) -> None:
    """删除分片目录及全部分片文件。"""
    shutil.rmtree(chunk_dir_path(upload_id), ignore_errors=True)
