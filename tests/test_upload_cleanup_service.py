"""UploadCleanupService 单元测试。

覆盖单次清理、状态过滤、临时目录清理与周期性运行。
"""

import asyncio
import time
from pathlib import Path

from app.constants import (
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_COMPLETING,
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_UPLOADING,
)
from app.models.upload_session import UploadSession
from app.repositories.upload_session_repository import (
    UploadSessionRepository,
)
from app.services.upload_cleanup_service import (
    MIN_CLEANUP_INTERVAL_SECONDS,
    UploadCleanupService,
)
from app.storage.upload_chunk_storage import LocalUploadChunkStorage


def build_service(
    tmp_path: Path,
    interval_seconds: float = 0.01,
) -> tuple[
    UploadCleanupService,
    UploadSessionRepository,
    LocalUploadChunkStorage,
]:
    """构造使用临时目录的清理服务及配套组件。

    Args:
        tmp_path: pytest 提供的临时目录。
        interval_seconds: 清理间隔。

    Returns:
        三元组 ``(service, repository, storage)``。
    """
    upload_temp_root = tmp_path / "upload_temp"
    upload_temp_root.mkdir(exist_ok=True)
    database_path = upload_temp_root / "uploads.sqlite3"
    repository = UploadSessionRepository(database_path)
    storage = LocalUploadChunkStorage(upload_temp_root)
    service = UploadCleanupService(repository, storage, interval_seconds)
    return service, repository, storage


def build_session(
    upload_id: str,
    status: str = STATUS_CREATED,
    expires_at: float = 1000.0,
) -> UploadSession:
    """构造测试用的会话对象。

    Args:
        upload_id: 会话 ID。
        status: 会话状态。
        expires_at: 过期时间戳。

    Returns:
        会话对象。
    """
    return UploadSession(
        upload_id=upload_id,
        target_path=f"/{upload_id}.bin",
        size=100,
        chunk_size=100,
        total_chunks=1,
        overwrite=False,
        checksum_algorithm=None,
        checksum_value=None,
        status=status,
        created_at=500.0,
        updated_at=500.0,
        expires_at=expires_at,
    )


def test_cleanup_once_returns_zero_when_no_sessions(
    tmp_path: Path,
) -> None:
    """无会话时应返回 0。"""
    service, _, _ = build_service(tmp_path)
    assert service.cleanup_once(now=2000.0) == 0


def test_cleanup_once_skips_active_sessions(tmp_path: Path) -> None:
    """未过期会话不应被清理。"""
    service, repository, _ = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_CREATED, expires_at=3000.0)
    )
    assert service.cleanup_once(now=2000.0) == 0
    session = repository.get_session("s1")
    assert session is not None
    assert session.status == STATUS_CREATED


def test_cleanup_once_expires_created_session(tmp_path: Path) -> None:
    """过期且状态为 ``created`` 的会话应被标记为过期并清理目录。"""
    service, repository, storage = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_CREATED, expires_at=1500.0)
    )
    storage.ensure_session_directory("s1")

    assert service.cleanup_once(now=2000.0) == 1
    session = repository.get_session("s1")
    assert session is not None
    assert session.status == STATUS_EXPIRED
    assert not storage.session_root("s1").exists()


def test_cleanup_once_expires_uploading_session(tmp_path: Path) -> None:
    """过期且状态为 ``uploading`` 的会话应被标记为过期。"""
    service, repository, _ = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_UPLOADING, expires_at=1500.0)
    )

    assert service.cleanup_once(now=2000.0) == 1
    session = repository.get_session("s1")
    assert session is not None
    assert session.status == STATUS_EXPIRED


def test_cleanup_once_skips_completing_session(tmp_path: Path) -> None:
    """``completing`` 状态的会话不应被清理。"""
    service, repository, _ = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_COMPLETING, expires_at=1500.0)
    )
    assert service.cleanup_once(now=2000.0) == 0
    session = repository.get_session("s1")
    assert session is not None
    assert session.status == STATUS_COMPLETING


def test_cleanup_once_skips_completed_session(tmp_path: Path) -> None:
    """``completed`` 状态的会话不应被清理。"""
    service, repository, _ = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_COMPLETED, expires_at=1500.0)
    )
    assert service.cleanup_once(now=2000.0) == 0
    session = repository.get_session("s1")
    assert session is not None
    assert session.status == STATUS_COMPLETED


def test_cleanup_once_skips_canceled_session(tmp_path: Path) -> None:
    """``canceled`` 状态的会话不应被清理。"""
    service, repository, _ = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_CANCELED, expires_at=1500.0)
    )
    assert service.cleanup_once(now=2000.0) == 0


def test_cleanup_once_skips_already_expired(tmp_path: Path) -> None:
    """已是 ``expired`` 状态的会话不应重复处理。"""
    service, repository, _ = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_EXPIRED, expires_at=1500.0)
    )
    assert service.cleanup_once(now=2000.0) == 0


def test_cleanup_once_handles_multiple_sessions(tmp_path: Path) -> None:
    """多个过期会话应被一次性清理。"""
    service, repository, _ = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_CREATED, expires_at=1500.0)
    )
    repository.create_session(
        build_session("s2", status=STATUS_UPLOADING, expires_at=1400.0)
    )
    repository.create_session(
        build_session("s3", status=STATUS_CREATED, expires_at=5000.0)
    )

    assert service.cleanup_once(now=2000.0) == 2
    s1 = repository.get_session("s1")
    s2 = repository.get_session("s2")
    s3 = repository.get_session("s3")
    assert s1 is not None and s1.status == STATUS_EXPIRED
    assert s2 is not None and s2.status == STATUS_EXPIRED
    assert s3 is not None and s3.status == STATUS_CREATED


def test_cleanup_once_uses_current_time_when_not_provided(
    tmp_path: Path,
) -> None:
    """未提供 ``now`` 时应使用当前时间。"""
    service, repository, _ = build_service(tmp_path)
    past = time.time() - 3600
    repository.create_session(
        build_session("s1", status=STATUS_CREATED, expires_at=past)
    )
    assert service.cleanup_once() == 1


def test_cleanup_once_cleans_storage_directory(tmp_path: Path) -> None:
    """清理应递归删除会话的临时目录。"""
    service, repository, storage = build_service(tmp_path)
    repository.create_session(
        build_session("s1", status=STATUS_UPLOADING, expires_at=1500.0)
    )
    storage.ensure_session_directory("s1")
    (storage.chunks_directory("s1") / "0.part").write_bytes(b"x")
    assert storage.session_root("s1").is_dir()

    service.cleanup_once(now=2000.0)
    assert not storage.session_root("s1").exists()


def test_cleanup_interval_is_clamped(tmp_path: Path) -> None:
    """构造时对间隔取最小阈值，避免忙循环。"""
    service, _, _ = build_service(tmp_path, interval_seconds=0.0)
    assert service.interval_seconds >= MIN_CLEANUP_INTERVAL_SECONDS


def test_run_periodically_stops_on_event(tmp_path: Path) -> None:
    """设置停止事件后，周期性任务应及时退出。"""
    service, _, _ = build_service(tmp_path, interval_seconds=0.01)
    stop_event = asyncio.Event()

    async def scenario() -> None:
        task = asyncio.create_task(service.run_periodically(stop_event))
        await asyncio.sleep(0.05)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(scenario())


def test_run_periodically_executes_cleanup(tmp_path: Path) -> None:
    """周期性任务应在运行期间执行至少一次清理。"""
    service, repository, _ = build_service(tmp_path, interval_seconds=0.01)
    repository.create_session(
        build_session("s1", status=STATUS_CREATED, expires_at=0.0)
    )
    stop_event = asyncio.Event()

    async def scenario() -> None:
        task = asyncio.create_task(service.run_periodically(stop_event))
        await asyncio.sleep(0.05)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(scenario())
    session = repository.get_session("s1")
    assert session is not None
    assert session.status == STATUS_EXPIRED


def test_run_periodically_survives_cleanup_error(
    tmp_path: Path,
) -> None:
    """单次清理失败不应终止循环。"""
    service, _, _ = build_service(tmp_path, interval_seconds=0.01)
    call_count = [0]
    original_cleanup = service.cleanup_once

    def failing_cleanup(now=None):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("boom")
        return original_cleanup(now)

    service.cleanup_once = failing_cleanup  # type: ignore[method-assign]
    stop_event = asyncio.Event()

    async def scenario() -> None:
        task = asyncio.create_task(service.run_periodically(stop_event))
        await asyncio.sleep(0.05)
        stop_event.set()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(scenario())
    assert call_count[0] >= 2
