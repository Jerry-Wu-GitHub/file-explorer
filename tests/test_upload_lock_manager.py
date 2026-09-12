"""UploadLockManager 单元测试。

覆盖基本获取/释放、同一锁的互斥性、不同锁的并行性以及跨线程行为。
"""

import threading
import time
from pathlib import Path

from app.storage.upload_lock_manager import UploadLockManager


def build_manager(tmp_path: Path) -> UploadLockManager:
    """构造使用临时目录的锁管理器。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        配置好的锁管理器。
    """
    return UploadLockManager(tmp_path / "locks")


def test_session_lock_acquire_and_release(tmp_path: Path) -> None:
    """获取与释放会话锁不应抛出异常。"""
    manager = build_manager(tmp_path)
    with manager.session_lock("u1"):
        pass
    with manager.session_lock("u1"):
        pass


def test_chunk_lock_acquire_and_release(tmp_path: Path) -> None:
    """获取与释放分片锁不应抛出异常。"""
    manager = build_manager(tmp_path)
    with manager.chunk_lock("u1", 0):
        pass
    with manager.chunk_lock("u1", 0):
        pass


def test_session_and_chunk_locks_are_independent(tmp_path: Path) -> None:
    """会话锁与分片锁为不同的锁文件，可同时持有。"""
    manager = build_manager(tmp_path)
    with manager.session_lock("u1"):
        with manager.chunk_lock("u1", 0):
            pass


def test_same_chunk_lock_is_exclusive(tmp_path: Path) -> None:
    """并发获取同一分片锁时，任一时刻只有一个线程持有。"""
    manager = build_manager(tmp_path)
    barrier = threading.Barrier(4)
    active_count = [0]
    max_concurrent = [0]
    counter_guard = threading.Lock()

    def worker() -> None:
        barrier.wait()
        with manager.chunk_lock("u1", 0):
            with counter_guard:
                active_count[0] += 1
                if active_count[0] > max_concurrent[0]:
                    max_concurrent[0] = active_count[0]
            time.sleep(0.02)
            with counter_guard:
                active_count[0] -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_concurrent[0] == 1


def test_different_chunks_can_hold_locks_in_parallel(
    tmp_path: Path,
) -> None:
    """不同分片编号的锁应能同时被持有。"""
    manager = build_manager(tmp_path)
    barrier = threading.Barrier(4)
    all_inside = threading.Barrier(4)

    def worker(chunk_number: int) -> None:
        barrier.wait()
        with manager.chunk_lock("u1", chunk_number):
            all_inside.wait(timeout=5)

    threads = [
        threading.Thread(target=worker, args=(index,)) for index in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_different_sessions_can_hold_locks_in_parallel(
    tmp_path: Path,
) -> None:
    """不同会话的会话锁应能同时被持有。"""
    manager = build_manager(tmp_path)
    barrier = threading.Barrier(3)
    all_inside = threading.Barrier(3)

    def worker(upload_id: str) -> None:
        barrier.wait()
        with manager.session_lock(upload_id):
            all_inside.wait(timeout=5)

    threads = [
        threading.Thread(target=worker, args=(f"u{index}",))
        for index in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_lock_release_on_exception(tmp_path: Path) -> None:
    """异常退出 ``with`` 时锁应被释放，后续可再次获取。"""
    manager = build_manager(tmp_path)
    try:
        with manager.session_lock("u1"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    with manager.session_lock("u1"):
        pass


def test_lock_root_created(tmp_path: Path) -> None:
    """构造时自动创建锁根目录。"""
    lock_root = tmp_path / "nested" / "locks"
    UploadLockManager(lock_root)
    assert lock_root.is_dir()


def test_lock_root_property(tmp_path: Path) -> None:
    """``lock_root`` 属性应返回解析后的绝对路径。"""
    manager = build_manager(tmp_path)
    assert manager.lock_root.is_absolute()
