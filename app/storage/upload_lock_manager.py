"""分片上传的文件锁管理。

本模块提供 :class:`UploadLockManager`，基于文件锁实现跨进程互斥。
在支持 :mod:`fcntl` 的平台上（Linux/macOS）使用 ``flock``：

- :meth:`session_read_lock`：``LOCK_SH`` 共享锁，多个分片上传可同时持有；
- :meth:`session_write_lock`：``LOCK_EX`` 排他锁，用于完成、取消等
  需要与所有分片上传互斥的操作；
- :meth:`chunk_lock`：以 ``uploadId + chunkNumber`` 为键的排他锁，
  串行化同一分片的并发上传。

在不支持 ``fcntl`` 的平台（Windows）上，会话锁退化为进程内读写锁，
分片锁退化为进程内互斥锁，仅保证同一进程内互斥，用于本地开发与
测试。
"""

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl

    _HAS_FCNTL: bool = True
except ImportError:  # pragma: no cover - 仅在 Windows 上触发
    _HAS_FCNTL = False


SESSION_LOCK_PREFIX: str = "session-"
"""会话级锁文件的前缀。"""

CHUNK_LOCK_PREFIX: str = "chunk-"
"""分片级锁文件的前缀。"""

LOCK_FILE_SUFFIX: str = ".lock"
"""锁文件的后缀。"""

LOCK_FILE_MODE: int = 0o600
"""锁文件的权限位。"""


class _ProcessReadWriteLock:
    """进程内读写锁。

    读锁可被多个线程同时持有；写锁排他。用于 Windows 平台上的
    会话级锁降级实现。
    """

    def __init__(self) -> None:
        """初始化读写锁。"""
        self._condition: threading.Condition = threading.Condition()
        self._reader_count: int = 0
        self._writer_active: bool = False

    def acquire_read(self) -> None:
        """获取读锁。"""
        with self._condition:
            while self._writer_active:
                self._condition.wait()
            self._reader_count += 1

    def release_read(self) -> None:
        """释放读锁。"""
        with self._condition:
            self._reader_count -= 1
            if self._reader_count == 0:
                self._condition.notify_all()

    def acquire_write(self) -> None:
        """获取写锁。"""
        with self._condition:
            while self._writer_active or self._reader_count > 0:
                self._condition.wait()
            self._writer_active = True

    def release_write(self) -> None:
        """释放写锁。"""
        with self._condition:
            self._writer_active = False
            self._condition.notify_all()


class UploadLockManager:
    """分片上传的锁管理器。

    Attributes:
        lock_root: 锁文件所在的根目录。
    """

    def __init__(self, lock_root: Path) -> None:
        """构造锁管理器。

        Args:
            lock_root: 锁文件根目录。
        """
        self._lock_root: Path = Path(lock_root).resolve()
        self._lock_root.mkdir(parents=True, exist_ok=True)
        self._process_mutex_locks: dict[str, threading.Lock] = {}
        self._process_rw_locks: dict[str, _ProcessReadWriteLock] = {}
        self._process_locks_guard: threading.Lock = threading.Lock()

    @property
    def lock_root(self) -> Path:
        """返回锁文件根目录。

        Returns:
            锁文件根目录绝对路径。
        """
        return self._lock_root

    @contextmanager
    def session_read_lock(self, upload_id: str) -> Iterator[None]:
        """获取会话级共享锁。

        多个持有者可同时进入，用于分片上传；与
        :meth:`session_write_lock` 互斥。

        Args:
            upload_id: 上传会话 ID。

        Yields:
            持有锁期间控制权交还给调用方。
        """
        lock_name = f"{SESSION_LOCK_PREFIX}{upload_id}{LOCK_FILE_SUFFIX}"
        with self._acquire_shared(lock_name):
            yield

    @contextmanager
    def session_write_lock(self, upload_id: str) -> Iterator[None]:
        """获取会话级排他锁。

        用于完成、取消等需要与所有分片上传互斥的操作。

        Args:
            upload_id: 上传会话 ID。

        Yields:
            持有锁期间控制权交还给调用方。
        """
        lock_name = f"{SESSION_LOCK_PREFIX}{upload_id}{LOCK_FILE_SUFFIX}"
        with self._acquire_exclusive(lock_name):
            yield

    @contextmanager
    def session_lock(self, upload_id: str) -> Iterator[None]:
        """获取会话级排他锁（向后兼容别名）。

        Args:
            upload_id: 上传会话 ID。

        Yields:
            持有锁期间控制权交还给调用方。
        """
        with self.session_write_lock(upload_id):
            yield

    @contextmanager
    def chunk_lock(
        self,
        upload_id: str,
        chunk_number: int,
    ) -> Iterator[None]:
        """获取分片级排他锁。

        不同 ``chunk_number`` 的锁互相独立，可并行持有。

        Args:
            upload_id: 上传会话 ID。
            chunk_number: 分片编号。

        Yields:
            持有锁期间控制权交还给调用方。
        """
        lock_name = (
            f"{CHUNK_LOCK_PREFIX}{upload_id}-{chunk_number}"
            f"{LOCK_FILE_SUFFIX}"
        )
        with self._acquire_exclusive(lock_name):
            yield

    @contextmanager
    def _acquire_shared(self, lock_name: str) -> Iterator[None]:
        """按平台获取共享锁。"""
        lock_path = self._lock_root / lock_name
        if _HAS_FCNTL:
            with self._acquire_flock(lock_path, shared=True):
                yield
        else:  # pragma: no cover - 仅在 Windows 上触发
            read_write_lock = self._get_read_write_lock(lock_path)
            read_write_lock.acquire_read()
            try:
                yield
            finally:
                read_write_lock.release_read()

    @contextmanager
    def _acquire_exclusive(self, lock_name: str) -> Iterator[None]:
        """按平台获取排他锁。"""
        lock_path = self._lock_root / lock_name
        if _HAS_FCNTL:
            with self._acquire_flock(lock_path, shared=False):
                yield
        elif lock_name.startswith(SESSION_LOCK_PREFIX):
            read_write_lock = self._get_read_write_lock(lock_path)
            read_write_lock.acquire_write()
            try:
                yield
            finally:
                read_write_lock.release_write()
        else:
            mutex_lock = self._get_mutex_lock(lock_path)
            mutex_lock.acquire()
            try:
                yield
            finally:
                mutex_lock.release()

    @contextmanager
    def _acquire_flock(
        self,
        lock_path: Path,
        shared: bool,
    ) -> Iterator[None]:
        """使用 ``fcntl.flock`` 获取锁。

        Args:
            lock_path: 锁文件路径。
            shared: 为 ``True`` 时使用共享锁 ``LOCK_SH``，否则使用
                排他锁 ``LOCK_EX``。

        Yields:
            持有锁期间控制权交还给调用方。
        """
        file_descriptor = os.open(
            str(lock_path),
            os.O_CREAT | os.O_RDWR,
            LOCK_FILE_MODE,
        )
        try:
            lock_flag = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(file_descriptor, lock_flag)
            try:
                yield
            finally:
                fcntl.flock(file_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(file_descriptor)

    def _get_read_write_lock(self, lock_path: Path) -> _ProcessReadWriteLock:
        """按锁文件路径获取或创建进程内读写锁。"""
        key = str(lock_path)
        with self._process_locks_guard:
            existing = self._process_rw_locks.get(key)
            if existing is not None:
                return existing
            new_lock = _ProcessReadWriteLock()
            self._process_rw_locks[key] = new_lock
            return new_lock

    def _get_mutex_lock(self, lock_path: Path) -> threading.Lock:
        """按锁文件路径获取或创建进程内互斥锁。"""
        key = str(lock_path)
        with self._process_locks_guard:
            existing = self._process_mutex_locks.get(key)
            if existing is not None:
                return existing
            new_lock = threading.Lock()
            self._process_mutex_locks[key] = new_lock
            return new_lock


__all__ = [
    "UploadLockManager",
    "SESSION_LOCK_PREFIX",
    "CHUNK_LOCK_PREFIX",
    "LOCK_FILE_SUFFIX",
]
