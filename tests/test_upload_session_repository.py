"""UploadSessionRepository 单元测试。

覆盖会话的创建、读取、状态转移、分片记录、快照计算、过期筛选与
删除级联，以及并发安全相关的原子操作。
"""

from pathlib import Path

import pytest

from app.constants import (
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_COMPLETING,
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_UPLOADING,
)
from app.errors import BusinessError, ErrorCode
from app.models.upload_session import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    UPLOAD_STATUSES,
    UploadChunkRecord,
    UploadSession,
)
from app.repositories.upload_session_repository import (
    UploadSessionRepository,
)


def build_repository(tmp_path: Path) -> UploadSessionRepository:
    """构造使用临时目录数据库的仓储。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        配置好的仓储实例。
    """
    return UploadSessionRepository(tmp_path / "uploads.sqlite3")


def build_session(
    upload_id: str = "session-1",
    target_path: str = "/docs/file.bin",
    size: int = 1000,
    chunk_size: int = 500,
    total_chunks: int = 2,
    overwrite: bool = False,
    checksum_algorithm: str | None = None,
    checksum_value: str | None = None,
    status: str = STATUS_CREATED,
    created_at: float = 1000.0,
    updated_at: float = 1000.0,
    expires_at: float = 2000.0,
) -> UploadSession:
    """构造测试用的会话对象。

    Returns:
        :class:`UploadSession` 实例。
    """
    return UploadSession(
        upload_id=upload_id,
        target_path=target_path,
        size=size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        overwrite=overwrite,
        checksum_algorithm=checksum_algorithm,
        checksum_value=checksum_value,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        expires_at=expires_at,
    )


def test_status_constants_are_consistent() -> None:
    """活动状态与终止状态应互斥且覆盖全部合法状态。"""
    active_set = set(ACTIVE_STATUSES)
    terminal_set = set(TERMINAL_STATUSES)
    assert active_set.isdisjoint(terminal_set)
    assert active_set | terminal_set == set(UPLOAD_STATUSES)


def test_create_and_get_session(tmp_path: Path) -> None:
    """创建会话后可按 ID 读取到相同内容。"""
    repository = build_repository(tmp_path)
    session = build_session(checksum_algorithm="sha256", checksum_value="abc")
    repository.create_session(session)

    loaded = repository.get_session("session-1")
    assert loaded is not None
    assert loaded.upload_id == "session-1"
    assert loaded.target_path == "/docs/file.bin"
    assert loaded.size == 1000
    assert loaded.chunk_size == 500
    assert loaded.total_chunks == 2
    assert loaded.overwrite is False
    assert loaded.checksum_algorithm == "sha256"
    assert loaded.checksum_value == "abc"
    assert loaded.status == STATUS_CREATED
    assert loaded.created_at == 1000.0
    assert loaded.expires_at == 2000.0


def test_create_session_persists_overwrite_flag(tmp_path: Path) -> None:
    """``overwrite=True`` 应被正确持久化。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session(overwrite=True))
    loaded = repository.get_session("session-1")
    assert loaded is not None
    assert loaded.overwrite is True


def test_get_session_returns_none_when_missing(tmp_path: Path) -> None:
    """读取不存在的会话返回 ``None``。"""
    repository = build_repository(tmp_path)
    assert repository.get_session("missing") is None


def test_create_session_rejects_duplicate_id(tmp_path: Path) -> None:
    """重复使用同一 ID 创建会话应抛出 ``CONFLICT``。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())
    with pytest.raises(BusinessError) as exc_info:
        repository.create_session(build_session())
    assert exc_info.value.code == ErrorCode.CONFLICT


def test_record_chunk_persists_and_lists(tmp_path: Path) -> None:
    """记录分片后应能在列表接口中读到。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())
    repository.record_chunk(
        UploadChunkRecord(
            upload_id="session-1",
            chunk_number=0,
            received_size=500,
            updated_at=1100.0,
        )
    )
    repository.record_chunk(
        UploadChunkRecord(
            upload_id="session-1",
            chunk_number=1,
            received_size=400,
            updated_at=1200.0,
        )
    )

    chunks = repository.list_chunks("session-1")
    assert [chunk.chunk_number for chunk in chunks] == [0, 1]
    assert [chunk.received_size for chunk in chunks] == [500, 400]


def test_record_chunk_is_idempotent(tmp_path: Path) -> None:
    """重复记录同一分片以最后一次写入为准。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())
    repository.record_chunk(
        UploadChunkRecord("session-1", 0, 500, 1100.0)
    )
    repository.record_chunk(
        UploadChunkRecord("session-1", 0, 480, 1200.0)
    )

    chunks = repository.list_chunks("session-1")
    assert len(chunks) == 1
    assert chunks[0].received_size == 480
    assert chunks[0].updated_at == 1200.0


def test_list_chunks_returns_empty_when_none(tmp_path: Path) -> None:
    """未上传分片时返回空列表。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())
    assert repository.list_chunks("session-1") == []


def test_get_snapshot_computes_derived_fields(tmp_path: Path) -> None:
    """快照应正确计算已上传分片与字节数。"""
    repository = build_repository(tmp_path)
    repository.create_session(
        build_session(size=1000, chunk_size=500, total_chunks=2)
    )
    repository.record_chunk(
        UploadChunkRecord("session-1", 0, 500, 1100.0)
    )

    snapshot = repository.get_snapshot("session-1")
    assert snapshot is not None
    assert snapshot.uploaded_chunks == [0]
    assert snapshot.uploaded_bytes == 500
    assert snapshot.missing_chunks == [1]


def test_get_snapshot_all_chunks_uploaded(tmp_path: Path) -> None:
    """所有分片上传后缺失列表为空。"""
    repository = build_repository(tmp_path)
    repository.create_session(
        build_session(size=1000, chunk_size=500, total_chunks=2)
    )
    repository.record_chunk(
        UploadChunkRecord("session-1", 0, 500, 1100.0)
    )
    repository.record_chunk(
        UploadChunkRecord("session-1", 1, 500, 1200.0)
    )

    snapshot = repository.get_snapshot("session-1")
    assert snapshot is not None
    assert snapshot.missing_chunks == []
    assert snapshot.uploaded_bytes == 1000


def test_get_snapshot_returns_none_when_missing(tmp_path: Path) -> None:
    """快照接口对不存在的会话返回 ``None``。"""
    repository = build_repository(tmp_path)
    assert repository.get_snapshot("missing") is None


def test_transition_status_success(tmp_path: Path) -> None:
    """合法转移应成功并持久化新状态。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())

    updated = repository.transition_status(
        "session-1",
        (STATUS_CREATED,),
        STATUS_UPLOADING,
        1100.0,
    )
    assert updated is True

    loaded = repository.get_session("session-1")
    assert loaded is not None
    assert loaded.status == STATUS_UPLOADING
    assert loaded.updated_at == 1100.0


def test_transition_status_rejects_wrong_current_state(
    tmp_path: Path,
) -> None:
    """当前状态不在期望集合中时不应更新。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session(status=STATUS_COMPLETED))

    updated = repository.transition_status(
        "session-1",
        (STATUS_CREATED, STATUS_UPLOADING),
        STATUS_COMPLETING,
        1100.0,
    )
    assert updated is False

    loaded = repository.get_session("session-1")
    assert loaded is not None
    assert loaded.status == STATUS_COMPLETED


def test_transition_status_second_call_is_noop(tmp_path: Path) -> None:
    """状态转移是原子的，第二次相同转移应失败。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())

    first = repository.transition_status(
        "session-1", (STATUS_CREATED,), STATUS_COMPLETING, 1100.0
    )
    second = repository.transition_status(
        "session-1", (STATUS_CREATED,), STATUS_COMPLETING, 1200.0
    )
    assert first is True
    assert second is False


def test_update_checksum(tmp_path: Path) -> None:
    """更新校验信息应持久化。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())

    repository.update_checksum("session-1", "sha256", "deadbeef", 1100.0)
    loaded = repository.get_session("session-1")
    assert loaded is not None
    assert loaded.checksum_algorithm == "sha256"
    assert loaded.checksum_value == "deadbeef"
    assert loaded.updated_at == 1100.0


def test_update_checksum_can_clear_values(tmp_path: Path) -> None:
    """更新校验信息为 ``None`` 时应清空。"""
    repository = build_repository(tmp_path)
    repository.create_session(
        build_session(checksum_algorithm="sha256", checksum_value="abc")
    )

    repository.update_checksum("session-1", None, None, 1100.0)
    loaded = repository.get_session("session-1")
    assert loaded is not None
    assert loaded.checksum_algorithm is None
    assert loaded.checksum_value is None


def test_delete_session_removes_chunks(tmp_path: Path) -> None:
    """删除会话应级联删除分片记录。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session())
    repository.record_chunk(
        UploadChunkRecord("session-1", 0, 500, 1100.0)
    )

    deleted = repository.delete_session("session-1")
    assert deleted is True
    assert repository.get_session("session-1") is None
    assert repository.list_chunks("session-1") == []


def test_delete_session_returns_false_when_missing(
    tmp_path: Path,
) -> None:
    """删除不存在的会话返回 ``False``。"""
    repository = build_repository(tmp_path)
    assert repository.delete_session("missing") is False


def test_count_active_sessions(tmp_path: Path) -> None:
    """活动会话计数只统计活动状态。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session(upload_id="a"))
    repository.create_session(build_session(upload_id="b"))
    repository.create_session(
        build_session(upload_id="c", status=STATUS_UPLOADING)
    )
    repository.create_session(
        build_session(upload_id="d", status=STATUS_COMPLETED)
    )
    repository.create_session(
        build_session(upload_id="e", status=STATUS_CANCELED)
    )

    assert repository.count_active_sessions() == 3


def test_count_active_sessions_empty(tmp_path: Path) -> None:
    """无会话时计数为 0。"""
    repository = build_repository(tmp_path)
    assert repository.count_active_sessions() == 0


def test_list_expired_sessions_filters_by_status(tmp_path: Path) -> None:
    """清理查询只返回活动状态且已过期的会话。"""
    repository = build_repository(tmp_path)
    repository.create_session(
        build_session(upload_id="a", status=STATUS_CREATED, expires_at=1500.0)
    )
    repository.create_session(
        build_session(
            upload_id="b", status=STATUS_UPLOADING, expires_at=1500.0
        )
    )
    repository.create_session(
        build_session(
            upload_id="c", status=STATUS_COMPLETED, expires_at=1500.0
        )
    )
    repository.create_session(
        build_session(
            upload_id="d", status=STATUS_COMPLETING, expires_at=1500.0
        )
    )
    repository.create_session(
        build_session(
            upload_id="e", status=STATUS_CREATED, expires_at=3000.0
        )
    )

    expired = repository.list_expired_sessions(now=2000.0)
    expired_ids = sorted(session.upload_id for session in expired)
    assert expired_ids == ["a", "b"]


def test_list_expired_sessions_empty(tmp_path: Path) -> None:
    """无过期会话时返回空列表。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session(expires_at=5000.0))
    assert repository.list_expired_sessions(now=2000.0) == []


def test_list_expired_sessions_sorted_by_expires_at(
    tmp_path: Path,
) -> None:
    """过期会话按过期时间升序返回。"""
    repository = build_repository(tmp_path)
    repository.create_session(
        build_session(upload_id="later", expires_at=1600.0)
    )
    repository.create_session(
        build_session(upload_id="earlier", expires_at=1200.0)
    )

    expired = repository.list_expired_sessions(now=2000.0)
    assert [session.upload_id for session in expired] == [
        "earlier",
        "later",
    ]


def test_repository_creates_missing_parent_directory(
    tmp_path: Path,
) -> None:
    """数据库文件所在的父目录不存在时自动创建。"""
    database_path = tmp_path / "nested" / "deeper" / "uploads.sqlite3"
    repository = UploadSessionRepository(database_path)
    repository.create_session(build_session())
    assert database_path.exists()


def test_repository_reopens_existing_database(tmp_path: Path) -> None:
    """重复打开同一数据库应保留既有数据。"""
    database_path = tmp_path / "uploads.sqlite3"
    first = UploadSessionRepository(database_path)
    first.create_session(build_session())

    second = UploadSessionRepository(database_path)
    loaded = second.get_session("session-1")
    assert loaded is not None
    assert loaded.upload_id == "session-1"


def test_session_with_expired_status_can_be_stored(tmp_path: Path) -> None:
    """终止状态可作为字段直接持久化，用于测试与历史恢复。"""
    repository = build_repository(tmp_path)
    repository.create_session(build_session(status=STATUS_EXPIRED))
    loaded = repository.get_session("session-1")
    assert loaded is not None
    assert loaded.status == STATUS_EXPIRED
