"""ChunkedUploadService 初始化与状态查询的单元测试。

覆盖成功初始化、各类参数校验、目标冲突、磁盘空间与并发会话限
制；状态查询部分覆盖正常会话、过期会话与已终止会话。

为便于控制磁盘空间与 TTL，本模块通过工厂函数灵活构造服务实例；
磁盘空间不足场景使用 :func:`unittest.mock.patch.object` 注入。
"""

import hashlib
import io
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Config
from app.constants import (
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_COMPLETING,
    STATUS_CREATED,
)
from app.errors import BusinessError, ErrorCode
from app.models.upload_session import UploadChunkRecord
from app.repositories.upload_session_repository import (
    UploadSessionRepository,
)
from app.schemas.upload import InitializeUploadRequest
from app.services.chunked_upload_service import ChunkedUploadService
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.storage.upload_chunk_storage import LocalUploadChunkStorage
from app.storage.upload_lock_manager import UploadLockManager


DEFAULT_CHUNK_SIZE: int = 1024 * 1024
"""测试中默认使用的分片大小（1 MiB）。"""

DEFAULT_TTL_SECONDS: int = 3600
"""测试中默认使用的会话有效期（1 小时）。"""


def build_service(
    tmp_path: Path,
    max_upload_size: int = 20 * 1024 * 1024 * 1024,
    max_chunks: int = 10000,
    max_concurrent_upload_sessions: int = 128,
    default_chunk_size: int = DEFAULT_CHUNK_SIZE,
    min_chunk_size: int = MIN_CHUNK_SIZE,
    max_chunk_size: int = MAX_CHUNK_SIZE,
    upload_session_ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> tuple[
    ChunkedUploadService,
    LocalUploadChunkStorage,
    UploadSessionRepository,
]:
    """构造使用临时目录的 ChunkedUploadService 及配套组件。

    Args:
        tmp_path: pytest 提供的临时目录。
        max_upload_size: 单个文件大小上限。
        max_chunks: 分片数量上限。
        max_concurrent_upload_sessions: 并发会话数上限。
        default_chunk_size: 默认分片大小。
        min_chunk_size: 允许的最小分片大小，默认使用常量。
        max_chunk_size: 允许的最大分片大小，默认使用常量。
        upload_session_ttl_seconds: 会话有效期（秒）。

    Returns:
        三元组 ``(service, storage, repository)``。
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    upload_temp_root = tmp_path / "upload_temp"
    upload_temp_root.mkdir(exist_ok=True)
    database_path = upload_temp_root / "uploads.sqlite3"

    config = Config(
        sandbox_root=sandbox,
        upload_temp_root=upload_temp_root,
        upload_database_path=database_path,
        max_upload_size=max_upload_size,
        max_chunks=max_chunks,
        max_concurrent_upload_sessions=max_concurrent_upload_sessions,
        default_chunk_size=default_chunk_size,
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        upload_session_ttl_seconds=upload_session_ttl_seconds,
    )
    path_service = PathService(config)
    metadata_service = MetadataService(path_service)
    repository = UploadSessionRepository(database_path)
    storage = LocalUploadChunkStorage(upload_temp_root)
    lock_manager = UploadLockManager(upload_temp_root / "locks")
    service = ChunkedUploadService(
        path_service,
        metadata_service,
        repository,
        storage,
        lock_manager,
        config,
    )
    return service, storage, repository


def test_initialize_single_chunk_file(tmp_path: Path) -> None:
    """小文件应生成 1 个分片，缺失列表包含 0。"""
    service, _, _ = build_service(tmp_path)
    response = service.initialize_upload(
        InitializeUploadRequest(path="/notes.txt", size=100)
    )
    assert response.upload_id
    assert response.path == "/notes.txt"
    assert response.size == 100
    assert response.chunk_size == DEFAULT_CHUNK_SIZE
    assert response.total_chunks == 1
    assert response.uploaded_chunks == []
    assert response.missing_chunks == [0]
    assert response.uploaded_bytes == 0
    assert response.status == STATUS_CREATED
    assert response.expires_at > response.created_at


def test_initialize_multi_chunk_file(tmp_path: Path) -> None:
    """大文件应生成 ceil(size / chunkSize) 个分片。"""
    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    response = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    assert response.chunk_size == 512
    assert response.total_chunks == 3
    assert response.missing_chunks == [0, 1, 2]


def test_initialize_zero_size_file(tmp_path: Path) -> None:
    """空文件 totalChunks 为 0 且缺失列表为空。"""
    service, _, _ = build_service(tmp_path)
    response = service.initialize_upload(
        InitializeUploadRequest(path="/empty.txt", size=0)
    )
    assert response.total_chunks == 0
    assert response.missing_chunks == []
    assert response.uploaded_chunks == []


def test_initialize_uses_requested_chunk_size(tmp_path: Path) -> None:
    """显式提供的 chunkSize 应被采用。"""
    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=1024 * 1024,
    )
    response = service.initialize_upload(
        InitializeUploadRequest(
            path="/large.bin", size=1000, chunk_size=1024 * 512
        )
    )
    assert response.chunk_size == 1024 * 512


def test_initialize_creates_session_directory(tmp_path: Path) -> None:
    """初始化应创建会话临时目录，但不创建目标文件。"""
    service, storage, _ = build_service(tmp_path)
    response = service.initialize_upload(
        InitializeUploadRequest(path="/notes.txt", size=100)
    )
    assert storage.session_root(response.upload_id).is_dir()
    sandbox = tmp_path / "sandbox"
    assert not (sandbox / "notes.txt").exists()


def test_initialize_rejects_trailing_slash(tmp_path: Path) -> None:
    """``path`` 以 / 结尾应返回 ``VALIDATION_ERROR``。"""
    service, _, _ = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(path="/documents/", size=100)
        )
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_initialize_rejects_missing_parent(tmp_path: Path) -> None:
    """父目录不存在应返回 ``PARENT_NOT_FOUND``。"""
    service, _, _ = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(path="/missing/a.txt", size=100)
        )
    assert exc_info.value.code == ErrorCode.PARENT_NOT_FOUND


def test_initialize_rejects_existing_file_without_overwrite(
    tmp_path: Path,
) -> None:
    """目标存在且不允许覆盖应返回 ``FILE_EXISTS``。"""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    (sandbox / "notes.txt").write_text("old", encoding="utf-8")
    service, _, _ = build_service(tmp_path)

    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(path="/notes.txt", size=100)
        )
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_initialize_allows_existing_file_with_overwrite(
    tmp_path: Path,
) -> None:
    """``overwrite=True`` 时允许目标已存在。"""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    (sandbox / "notes.txt").write_text("old", encoding="utf-8")
    service, _, _ = build_service(tmp_path)

    response = service.initialize_upload(
        InitializeUploadRequest(
            path="/notes.txt", size=100, overwrite=True
        )
    )
    assert response.upload_id


def test_initialize_rejects_existing_directory(tmp_path: Path) -> None:
    """目标是目录时应返回 ``FILE_EXISTS``，即使 overwrite=True。"""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    (sandbox / "docs").mkdir()
    service, _, _ = build_service(tmp_path)

    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(
                path="/docs", size=100, overwrite=True
            )
        )
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_initialize_rejects_parent_reference(tmp_path: Path) -> None:
    """含 ``..`` 的路径应返回 ``INVALID_PATH``。"""
    service, _, _ = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(path="/../evil.txt", size=100)
        )
    assert exc_info.value.code == ErrorCode.INVALID_PATH


def test_initialize_rejects_oversized_size(tmp_path: Path) -> None:
    """``size`` 超过上限应返回 ``PAYLOAD_TOO_LARGE``。"""
    service, _, _ = build_service(tmp_path, max_upload_size=1024)
    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(path="/big.bin", size=2048)
        )
    assert exc_info.value.code == ErrorCode.PAYLOAD_TOO_LARGE


def test_initialize_rejects_too_many_chunks(tmp_path: Path) -> None:
    """分片数超过上限应返回 ``VALIDATION_ERROR``。"""
    service, _, _ = build_service(
        tmp_path,
        max_chunks=2,
        default_chunk_size=256 * 1024,
    )
    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(path="/big.bin", size=10 * 1024 * 1024)
        )
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_initialize_rejects_too_many_active_sessions(
    tmp_path: Path,
) -> None:
    """活动会话数达到上限应返回 ``CONFLICT``。"""
    service, _, _ = build_service(
        tmp_path, max_concurrent_upload_sessions=2
    )
    service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    service.initialize_upload(
        InitializeUploadRequest(path="/b.bin", size=100)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.initialize_upload(
            InitializeUploadRequest(path="/c.bin", size=100)
        )
    assert exc_info.value.code == ErrorCode.CONFLICT


def test_initialize_rejects_insufficient_disk_space(
    tmp_path: Path,
) -> None:
    """磁盘空间不足应返回 ``INSUFFICIENT_STORAGE``。"""
    service, storage, _ = build_service(tmp_path)
    with patch.object(
        storage, "available_disk_space_bytes", return_value=0
    ):
        with pytest.raises(BusinessError) as exc_info:
            service.initialize_upload(
                InitializeUploadRequest(path="/a.bin", size=100)
            )
        assert exc_info.value.code == ErrorCode.INSUFFICIENT_STORAGE


def test_initialize_persists_checksum(tmp_path: Path) -> None:
    """初始化时应持久化校验信息。"""
    service, _, repository = build_service(tmp_path)
    response = service.initialize_upload(
        InitializeUploadRequest(
            path="/a.bin",
            size=100,
            checksum={"algorithm": "sha256", "value": "deadbeef"},
        )
    )
    session = repository.get_session(response.upload_id)
    assert session is not None
    assert session.checksum_algorithm == "sha256"
    assert session.checksum_value == "deadbeef"


def test_get_status_returns_created_session(tmp_path: Path) -> None:
    """刚初始化的会话应返回 ``created`` 状态。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    status = service.get_upload_status(created.upload_id)
    assert status.upload_id == created.upload_id
    assert status.status == STATUS_CREATED
    assert status.uploaded_chunks == []
    assert status.missing_chunks == created.missing_chunks


def test_get_status_reflects_uploaded_chunks(tmp_path: Path) -> None:
    """已上传分片应体现在状态查询结果中。"""
    service, storage, repository = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=1500)
    )
    storage.write_chunk(
        created.upload_id, 0, io.BytesIO(b"x" * 512), expected_size=512
    )
    repository.record_chunk(
        UploadChunkRecord(created.upload_id, 0, 512, 0.0)
    )

    status = service.get_upload_status(created.upload_id)
    assert status.uploaded_chunks == [0]
    assert status.missing_chunks == [1, 2]
    assert status.uploaded_bytes == 512
    assert status.status == STATUS_CREATED


def test_get_status_returns_completed_session(tmp_path: Path) -> None:
    """已完成的会话应返回 ``completed`` 状态而非异常。"""
    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    repository.transition_status(
        created.upload_id,
        (STATUS_CREATED,),
        STATUS_COMPLETED,
        0.0,
    )
    status = service.get_upload_status(created.upload_id)
    assert status.status == STATUS_COMPLETED


def test_get_status_returns_canceled_session(tmp_path: Path) -> None:
    """已取消的会话应返回 ``canceled`` 状态而非异常。"""
    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    repository.transition_status(
        created.upload_id,
        (STATUS_CREATED,),
        STATUS_CANCELED,
        0.0,
    )
    status = service.get_upload_status(created.upload_id)
    assert status.status == STATUS_CANCELED


def test_get_status_marks_expired_session(tmp_path: Path) -> None:
    """超过 ``expiresAt`` 后状态查询应返回 ``UPLOAD_EXPIRED``。"""
    service, storage, repository = build_service(
        tmp_path, upload_session_ttl_seconds=0
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    assert storage.session_root(created.upload_id).is_dir()

    with pytest.raises(BusinessError) as exc_info:
        service.get_upload_status(created.upload_id)
    assert exc_info.value.code == ErrorCode.UPLOAD_EXPIRED

    session = repository.get_session(created.upload_id)
    assert session is not None
    assert session.status == "expired"


def test_get_status_rejects_nonexistent(tmp_path: Path) -> None:
    """不存在的会话 ID 应返回 ``UPLOAD_NOT_FOUND``。"""
    service, _, _ = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.get_upload_status("not-a-real-id")
    assert exc_info.value.code == ErrorCode.UPLOAD_NOT_FOUND


def test_get_status_does_not_expire_completing_session(
    tmp_path: Path,
) -> None:
    """``completing`` 状态的会话不应被标记为过期。"""
    service, _, repository = build_service(
        tmp_path, upload_session_ttl_seconds=0
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    repository.transition_status(
        created.upload_id,
        (STATUS_CREATED,),
        STATUS_COMPLETING,
        0.0,
    )
    status = service.get_upload_status(created.upload_id)
    assert status.status == STATUS_COMPLETING



# ---------- 上传分片：成功路径 ----------


def test_upload_chunk_single_chunk_file(tmp_path: Path) -> None:
    """小文件单分片上传应成功并转移状态到 uploading。"""
    service, storage, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/notes.txt", size=100)
    )

    response = service.upload_chunk(
        created.upload_id, 0, io.BytesIO(b"a" * 100)
    )
    assert response.upload_id == created.upload_id
    assert response.chunk_number == 0
    assert response.received_size == 100
    assert response.uploaded_chunks == 1
    assert response.total_chunks == 1
    assert response.uploaded_bytes == 100
    assert response.status == "uploading"
    assert storage.chunk_path(created.upload_id, 0).exists()

    session = repository.get_session(created.upload_id)
    assert session is not None
    assert session.status == "uploading"


def test_upload_chunk_multi_chunks_in_order(tmp_path: Path) -> None:
    """按顺序上传多个分片应累积 uploadedBytes。"""
    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )

    first = service.upload_chunk(
        created.upload_id, 0, io.BytesIO(b"a" * 512)
    )
    assert first.uploaded_chunks == 1
    assert first.uploaded_bytes == 512

    second = service.upload_chunk(
        created.upload_id, 1, io.BytesIO(b"b" * 512)
    )
    assert second.uploaded_chunks == 2
    assert second.uploaded_bytes == 1024

    third = service.upload_chunk(
        created.upload_id, 2, io.BytesIO(b"c" * 476)
    )
    assert third.uploaded_chunks == 3
    assert third.uploaded_bytes == 1500
    assert third.status == "uploading"


def test_upload_chunk_out_of_order(tmp_path: Path) -> None:
    """乱序上传分片应成功并正确累积。"""
    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )

    service.upload_chunk(created.upload_id, 2, io.BytesIO(b"c" * 476))
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 512))
    response = service.upload_chunk(
        created.upload_id, 1, io.BytesIO(b"b" * 512)
    )
    assert response.uploaded_chunks == 3
    assert response.uploaded_bytes == 1500


def test_upload_chunk_repeat_is_idempotent(tmp_path: Path) -> None:
    """重复上传同一分片以最后一次为准，计数不重复累加。"""
    service, storage, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/notes.txt", size=100)
    )

    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    response = service.upload_chunk(
        created.upload_id, 0, io.BytesIO(b"b" * 100)
    )
    assert response.uploaded_chunks == 1
    assert response.uploaded_bytes == 100
    assert (
        storage.chunk_path(created.upload_id, 0).read_bytes() == b"b" * 100
    )


def test_upload_chunk_last_chunk_size_can_be_smaller(
    tmp_path: Path,
) -> None:
    """最后一片允许小于 chunkSize。"""
    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    response = service.upload_chunk(
        created.upload_id, 2, io.BytesIO(b"x" * 476)
    )
    assert response.received_size == 476


# ---------- 上传分片：校验和 ----------


def test_upload_chunk_md5_checksum_passes(tmp_path: Path) -> None:
    """提供正确的 MD5 应通过校验。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    payload = b"x" * 100
    md5_hex = hashlib.md5(payload).hexdigest()
    response = service.upload_chunk(
        created.upload_id, 0, io.BytesIO(payload), content_md5=md5_hex
    )
    assert response.received_size == 100


def test_upload_chunk_md5_checksum_mismatch(tmp_path: Path) -> None:
    """MD5 不匹配应返回 ``CHECKSUM_MISMATCH``，且不保存分片。"""
    service, storage, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(
            created.upload_id,
            0,
            io.BytesIO(b"x" * 100),
            content_md5="0" * 32,
        )
    assert exc_info.value.code == ErrorCode.CHECKSUM_MISMATCH
    assert not storage.chunk_path(created.upload_id, 0).exists()
    assert repository.list_chunks(created.upload_id) == []


def test_upload_chunk_sha256_checksum_passes(tmp_path: Path) -> None:
    """提供正确的 SHA-256 应通过校验。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    payload = b"y" * 100
    sha_hex = hashlib.sha256(payload).hexdigest()
    response = service.upload_chunk(
        created.upload_id, 0, io.BytesIO(payload), chunk_sha256=sha_hex
    )
    assert response.received_size == 100


def test_upload_chunk_sha256_checksum_mismatch(tmp_path: Path) -> None:
    """SHA-256 不匹配应返回 ``CHECKSUM_MISMATCH``。"""
    service, storage, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(
            created.upload_id,
            0,
            io.BytesIO(b"x" * 100),
            chunk_sha256="0" * 64,
        )
    assert exc_info.value.code == ErrorCode.CHECKSUM_MISMATCH
    assert not storage.chunk_path(created.upload_id, 0).exists()


def test_upload_chunk_checksum_case_insensitive(tmp_path: Path) -> None:
    """校验值大小写应不敏感。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    payload = b"x" * 100
    md5_upper = hashlib.md5(payload).hexdigest().upper()
    response = service.upload_chunk(
        created.upload_id, 0, io.BytesIO(payload), content_md5=md5_upper
    )
    assert response.received_size == 100


# ---------- 上传分片：大小校验 ----------


def test_upload_chunk_rejects_size_too_small(tmp_path: Path) -> None:
    """非最后一片小于 chunkSize 应返回 ``INVALID_CHUNK_SIZE``。"""
    service, storage, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 0, io.BytesIO(b"x" * 100))
    assert exc_info.value.code == ErrorCode.INVALID_CHUNK_SIZE
    assert not storage.chunk_path(created.upload_id, 0).exists()


def test_upload_chunk_rejects_size_too_large(tmp_path: Path) -> None:
    """非最后一片大于 chunkSize 应返回 ``INVALID_CHUNK_SIZE``。"""
    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 0, io.BytesIO(b"x" * 600))
    assert exc_info.value.code == ErrorCode.INVALID_CHUNK_SIZE


def test_upload_chunk_last_chunk_size_mismatch(tmp_path: Path) -> None:
    """最后一片大小不符应返回 ``INVALID_CHUNK_SIZE``。"""
    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 2, io.BytesIO(b"x" * 500))
    assert exc_info.value.code == ErrorCode.INVALID_CHUNK_SIZE


# ---------- 上传分片：编号越界 ----------


def test_upload_chunk_rejects_negative_chunk_number(tmp_path: Path) -> None:
    """负数编号应返回 ``CHUNK_OUT_OF_RANGE``。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, -1, io.BytesIO(b"x"))
    assert exc_info.value.code == ErrorCode.CHUNK_OUT_OF_RANGE


def test_upload_chunk_rejects_chunk_number_at_boundary(
    tmp_path: Path,
) -> None:
    """编号等于 totalChunks 应返回 ``CHUNK_OUT_OF_RANGE``。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 1, io.BytesIO(b"x"))
    assert exc_info.value.code == ErrorCode.CHUNK_OUT_OF_RANGE


def test_upload_chunk_rejects_chunk_for_empty_file(tmp_path: Path) -> None:
    """空文件没有任何分片，任何编号都应越界。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/empty.bin", size=0)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 0, io.BytesIO(b"x"))
    assert exc_info.value.code == ErrorCode.CHUNK_OUT_OF_RANGE


# ---------- 上传分片：状态机拒绝 ----------


def test_upload_chunk_rejects_completing_session(tmp_path: Path) -> None:
    """``completing`` 状态应返回 ``UPLOAD_COMPLETING``。"""
    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    repository.transition_status(
        created.upload_id, ("created",), "completing", 0.0
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 0, io.BytesIO(b"x" * 100))
    assert exc_info.value.code == ErrorCode.UPLOAD_COMPLETING


def test_upload_chunk_rejects_completed_session(tmp_path: Path) -> None:
    """``completed`` 状态应返回 ``UPLOAD_ALREADY_COMPLETED``。"""
    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    repository.transition_status(
        created.upload_id, ("created",), "completed", 0.0
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 0, io.BytesIO(b"x" * 100))
    assert exc_info.value.code == ErrorCode.UPLOAD_ALREADY_COMPLETED


def test_upload_chunk_rejects_canceled_session(tmp_path: Path) -> None:
    """``canceled`` 状态应返回 ``UPLOAD_CANCELED``。"""
    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    repository.transition_status(
        created.upload_id, ("created",), "canceled", 0.0
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 0, io.BytesIO(b"x" * 100))
    assert exc_info.value.code == ErrorCode.UPLOAD_CANCELED


def test_upload_chunk_rejects_expired_session(tmp_path: Path) -> None:
    """已过期会话应返回 ``UPLOAD_EXPIRED``。"""
    service, _, _ = build_service(
        tmp_path, upload_session_ttl_seconds=0
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(created.upload_id, 0, io.BytesIO(b"x" * 100))
    assert exc_info.value.code == ErrorCode.UPLOAD_EXPIRED


def test_upload_chunk_rejects_nonexistent_session(tmp_path: Path) -> None:
    """不存在的会话 ID 应返回 ``UPLOAD_NOT_FOUND``。"""
    service, _, _ = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.upload_chunk(
            "not-a-real-id", 0, io.BytesIO(b"x")
        )
    assert exc_info.value.code == ErrorCode.UPLOAD_NOT_FOUND


# ---------- 上传分片：并发 ----------


def test_upload_chunk_different_chunks_are_isolated(
    tmp_path: Path,
) -> None:
    """不同分片并发上传互不干扰。"""
    service, storage, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    barrier = threading.Barrier(3)
    payloads = [b"a" * 512, b"b" * 512, b"c" * 476]

    def worker(chunk_number: int) -> None:
        barrier.wait()
        service.upload_chunk(
            created.upload_id,
            chunk_number,
            io.BytesIO(payloads[chunk_number]),
        )

    threads = [
        threading.Thread(target=worker, args=(index,)) for index in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert storage.list_uploaded_chunks(created.upload_id) == [0, 1, 2]
    assert (
        storage.chunk_path(created.upload_id, 0).read_bytes() == payloads[0]
    )
    assert (
        storage.chunk_path(created.upload_id, 1).read_bytes() == payloads[1]
    )
    assert (
        storage.chunk_path(created.upload_id, 2).read_bytes() == payloads[2]
    )


def test_upload_chunk_same_chunk_serialized(tmp_path: Path) -> None:
    """同一分片并发上传应串行化，最终内容为某一次完整写入。"""
    service, storage, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.bin", size=100)
    )
    barrier = threading.Barrier(4)
    payloads = [bytes([index]) * 100 for index in range(4)]

    def worker(index: int) -> None:
        barrier.wait()
        service.upload_chunk(
            created.upload_id, 0, io.BytesIO(payloads[index])
        )

    threads = [
        threading.Thread(target=worker, args=(index,)) for index in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    final = storage.chunk_path(created.upload_id, 0).read_bytes()
    assert len(final) == 100
    assert len(set(final)) == 1
    assert final in payloads

    chunks = repository.list_chunks(created.upload_id)
    assert len(chunks) == 1
    assert chunks[0].received_size == 100


# ---------- 完成上传：成功路径 ----------


def _upload_all_chunks(
    service,
    upload_id: str,
    size: int,
    chunk_size: int,
) -> None:
    """辅助函数：按序上传指定会话的所有分片。

    Args:
        service: 服务实例。
        upload_id: 上传会话 ID。
        size: 文件总字节数。
        chunk_size: 分片大小。
    """
    if size == 0:
        return
    total_chunks = (size + chunk_size - 1) // chunk_size
    for chunk_number in range(total_chunks):
        remaining = size - chunk_size * chunk_number
        this_size = min(chunk_size, remaining)
        service.upload_chunk(
            upload_id,
            chunk_number,
            io.BytesIO(bytes([chunk_number % 256]) * this_size),
        )


def test_complete_upload_single_chunk(tmp_path: Path) -> None:
    """单分片会话完成后应生成目标文件与元数据。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/notes.txt", size=100)
    )
    service.upload_chunk(
        created.upload_id, 0, io.BytesIO(b"a" * 100)
    )

    metadata = service.complete_upload(
        created.upload_id, CompleteUploadRequest()
    )
    assert metadata.name == "notes.txt"
    assert metadata.path == "/notes.txt"
    assert metadata.type == "file"
    assert metadata.size == 100
    sandbox = tmp_path / "sandbox"
    assert (sandbox / "notes.txt").read_bytes() == b"a" * 100


def test_complete_upload_multi_chunks_in_order(tmp_path: Path) -> None:
    """多分片完成后内容应按顺序拼接。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 512))
    service.upload_chunk(created.upload_id, 1, io.BytesIO(b"b" * 512))
    service.upload_chunk(created.upload_id, 2, io.BytesIO(b"c" * 476))

    metadata = service.complete_upload(
        created.upload_id, CompleteUploadRequest()
    )
    assert metadata.size == 1500
    sandbox = tmp_path / "sandbox"
    assert (sandbox / "large.bin").read_bytes() == (
        b"a" * 512 + b"b" * 512 + b"c" * 476
    )


def test_complete_upload_zero_size_file(tmp_path: Path) -> None:
    """空文件完成后应生成空文件。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/empty.txt", size=0)
    )
    metadata = service.complete_upload(
        created.upload_id, CompleteUploadRequest()
    )
    assert metadata.size == 0
    assert (tmp_path / "sandbox" / "empty.txt").read_bytes() == b""


def test_complete_upload_cleans_temp_chunks(tmp_path: Path) -> None:
    """完成后应清理临时分片。"""
    from app.schemas.upload import CompleteUploadRequest

    service, storage, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert not storage.session_root(created.upload_id).exists()


def test_complete_upload_marks_session_completed(tmp_path: Path) -> None:
    """完成后会话状态应持久化为 ``completed``。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    service.complete_upload(created.upload_id, CompleteUploadRequest())

    session = repository.get_session(created.upload_id)
    assert session is not None
    assert session.status == "completed"


def test_complete_upload_repeat_returns_metadata(tmp_path: Path) -> None:
    """重复调用完成接口应返回现有文件元数据。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    first = service.complete_upload(
        created.upload_id, CompleteUploadRequest()
    )
    second = service.complete_upload(
        created.upload_id, CompleteUploadRequest()
    )
    assert first.path == second.path
    assert first.size == second.size


def test_complete_upload_overwrites_existing_target(tmp_path: Path) -> None:
    """``overwrite=True`` 时允许覆盖已存在目标。"""
    from app.schemas.upload import CompleteUploadRequest

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    (sandbox / "a.txt").write_text("old", encoding="utf-8")
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100, overwrite=True)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert (sandbox / "a.txt").read_bytes() == b"a" * 100


# ---------- 完成上传：缺失分片 ----------


def test_complete_upload_rejects_missing_chunks(tmp_path: Path) -> None:
    """缺失分片应返回 ``UPLOAD_INCOMPLETE`` 并携带缺失列表。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 512))

    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert exc_info.value.code == ErrorCode.UPLOAD_INCOMPLETE
    assert exc_info.value.details == {"missingChunks": [1, 2]}


def test_complete_upload_failure_reverts_to_uploading(
    tmp_path: Path,
) -> None:
    """缺失分片失败后状态应回退到 ``uploading``，允许继续上传。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, repository = build_service(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/large.bin", size=1500)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 512))

    with pytest.raises(BusinessError):
        service.complete_upload(created.upload_id, CompleteUploadRequest())

    session = repository.get_session(created.upload_id)
    assert session is not None
    assert session.status == "uploading"


# ---------- 完成上传：整体 checksum ----------


def test_complete_upload_checksum_passes(tmp_path: Path) -> None:
    """提供正确的整体 checksum 应通过校验。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    payload = b"a" * 100
    digest = hashlib.sha256(payload).hexdigest()
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(payload))

    metadata = service.complete_upload(
        created.upload_id,
        CompleteUploadRequest(
            checksum={"algorithm": "sha256", "value": digest}
        ),
    )
    assert metadata.size == 100


def test_complete_upload_checksum_mismatch(tmp_path: Path) -> None:
    """整体校验失败应返回 ``CHECKSUM_MISMATCH`` 且不生成目标文件。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))

    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload(
            created.upload_id,
            CompleteUploadRequest(
                checksum={"algorithm": "sha256", "value": "0" * 64}
            ),
        )
    assert exc_info.value.code == ErrorCode.CHECKSUM_MISMATCH
    assert not (tmp_path / "sandbox" / "a.txt").exists()


def test_complete_upload_checksum_from_initialization(
    tmp_path: Path,
) -> None:
    """初始化时提供的 checksum 应在完成时生效。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    payload = b"a" * 100
    digest = hashlib.sha256(payload).hexdigest()
    created = service.initialize_upload(
        InitializeUploadRequest(
            path="/a.txt",
            size=100,
            checksum={"algorithm": "sha256", "value": digest},
        )
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(payload))
    metadata = service.complete_upload(
        created.upload_id, CompleteUploadRequest()
    )
    assert metadata.size == 100


def test_complete_upload_checksum_overrides_initialization(
    tmp_path: Path,
) -> None:
    """完成请求中的 checksum 优先于初始化时提供的值。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    payload = b"a" * 100
    wrong_digest = "0" * 64
    correct_digest = hashlib.sha256(payload).hexdigest()
    created = service.initialize_upload(
        InitializeUploadRequest(
            path="/a.txt",
            size=100,
            checksum={"algorithm": "sha256", "value": wrong_digest},
        )
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(payload))
    metadata = service.complete_upload(
        created.upload_id,
        CompleteUploadRequest(
            checksum={"algorithm": "sha256", "value": correct_digest}
        ),
    )
    assert metadata.size == 100


def test_complete_upload_checksum_failure_reverts_status(
    tmp_path: Path,
) -> None:
    """整体校验失败后状态应回退到 ``uploading``。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))

    with pytest.raises(BusinessError):
        service.complete_upload(
            created.upload_id,
            CompleteUploadRequest(
                checksum={"algorithm": "sha256", "value": "0" * 64}
            ),
        )

    session = repository.get_session(created.upload_id)
    assert session is not None
    assert session.status == "uploading"


# ---------- 完成上传：状态机拒绝 ----------


def test_complete_upload_rejects_canceled_session(tmp_path: Path) -> None:
    """已取消会话应返回 ``UPLOAD_CANCELED``。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    repository.transition_status(
        created.upload_id, ("created",), "canceled", 0.0
    )
    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert exc_info.value.code == ErrorCode.UPLOAD_CANCELED


def test_complete_upload_rejects_expired_session(tmp_path: Path) -> None:
    """已过期会话应返回 ``UPLOAD_EXPIRED``。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(
        tmp_path, upload_session_ttl_seconds=0
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert exc_info.value.code == ErrorCode.UPLOAD_EXPIRED


def test_complete_upload_rejects_nonexistent(tmp_path: Path) -> None:
    """不存在的会话 ID 应返回 ``UPLOAD_NOT_FOUND``。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload("not-a-real-id", CompleteUploadRequest())
    assert exc_info.value.code == ErrorCode.UPLOAD_NOT_FOUND


# ---------- 完成上传：目标二次校验 ----------


def test_complete_upload_rejects_target_directory_created_after_init(
    tmp_path: Path,
) -> None:
    """分片期间目标变成目录时，完成应返回 ``FILE_EXISTS``。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    (tmp_path / "sandbox" / "a.txt").mkdir()

    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_complete_upload_rejects_target_created_after_init(
    tmp_path: Path,
) -> None:
    """分片期间目标文件被创建且 ``overwrite=False`` 时应冲突。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    (tmp_path / "sandbox" / "a.txt").write_text("intruder", encoding="utf-8")

    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_complete_upload_rejects_missing_parent_after_init(
    tmp_path: Path,
) -> None:
    """分片期间父目录被删除时，完成应返回 ``PARENT_NOT_FOUND``。"""
    from app.schemas.upload import CompleteUploadRequest

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    (sandbox / "docs").mkdir()
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/docs/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    (sandbox / "docs").rmdir()

    with pytest.raises(BusinessError) as exc_info:
        service.complete_upload(created.upload_id, CompleteUploadRequest())
    assert exc_info.value.code == ErrorCode.PARENT_NOT_FOUND


# ---------- 完成上传：磁盘空间 ----------


def test_complete_upload_rejects_insufficient_disk_space(
    tmp_path: Path,
) -> None:
    """磁盘空间不足时完成应返回 ``INSUFFICIENT_STORAGE``。"""
    from unittest.mock import patch

    from app.schemas.upload import CompleteUploadRequest

    service, storage, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))

    with patch.object(
        storage, "available_disk_space_bytes", return_value=0
    ):
        with pytest.raises(BusinessError) as exc_info:
            service.complete_upload(
                created.upload_id, CompleteUploadRequest()
            )
        assert exc_info.value.code == ErrorCode.INSUFFICIENT_STORAGE


# ---------- 完成上传：无临时文件残留 ----------


def test_complete_upload_no_merge_temp_left_on_checksum_failure(
    tmp_path: Path,
) -> None:
    """整体校验失败后不应残留合并临时文件。"""
    from app.constants import MERGE_TEMP_SUFFIX
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))

    with pytest.raises(BusinessError):
        service.complete_upload(
            created.upload_id,
            CompleteUploadRequest(
                checksum={"algorithm": "sha256", "value": "0" * 64}
            ),
        )

    sandbox = tmp_path / "sandbox"
    leftovers = [
        entry
        for entry in sandbox.iterdir()
        if entry.name.endswith(MERGE_TEMP_SUFFIX)
    ]
    assert leftovers == []


# ---------- 取消上传 ----------


def test_cancel_upload_removes_session_and_files(tmp_path: Path) -> None:
    """取消应删除会话记录与临时分片。"""
    service, storage, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))

    service.cancel_upload(created.upload_id)

    assert repository.get_session(created.upload_id) is None
    assert not storage.session_root(created.upload_id).exists()


def test_cancel_upload_is_idempotent(tmp_path: Path) -> None:
    """重复取消应静默返回。"""
    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.cancel_upload(created.upload_id)
    service.cancel_upload(created.upload_id)


def test_cancel_upload_nonexistent_is_noop(tmp_path: Path) -> None:
    """不存在的会话 ID 应静默返回，不抛异常。"""
    service, _, _ = build_service(tmp_path)
    service.cancel_upload("not-a-real-id")


def test_cancel_upload_rejects_completed(tmp_path: Path) -> None:
    """已完成的会话应返回 ``UPLOAD_ALREADY_COMPLETED``，且不删除目标文件。"""
    from app.schemas.upload import CompleteUploadRequest

    service, _, _ = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    service.upload_chunk(created.upload_id, 0, io.BytesIO(b"a" * 100))
    service.complete_upload(created.upload_id, CompleteUploadRequest())

    with pytest.raises(BusinessError) as exc_info:
        service.cancel_upload(created.upload_id)
    assert exc_info.value.code == ErrorCode.UPLOAD_ALREADY_COMPLETED
    assert (tmp_path / "sandbox" / "a.txt").exists()


def test_cancel_upload_rejects_completing(tmp_path: Path) -> None:
    """``completing`` 状态的会话应返回 ``UPLOAD_COMPLETING``。"""
    service, _, repository = build_service(tmp_path)
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    repository.transition_status(
        created.upload_id, ("created",), "completing", 0.0
    )
    with pytest.raises(BusinessError) as exc_info:
        service.cancel_upload(created.upload_id)
    assert exc_info.value.code == ErrorCode.UPLOAD_COMPLETING


def test_cancel_upload_expired_session_returns_cleanly(
    tmp_path: Path,
) -> None:
    """已过期会话取消应静默清理并删除元数据。"""
    service, storage, repository = build_service(
        tmp_path, upload_session_ttl_seconds=0
    )
    created = service.initialize_upload(
        InitializeUploadRequest(path="/a.txt", size=100)
    )
    # 首次触发过期标记
    with pytest.raises(BusinessError):
        service.get_upload_status(created.upload_id)

    service.cancel_upload(created.upload_id)
    assert repository.get_session(created.upload_id) is None
    assert not storage.session_root(created.upload_id).exists()
