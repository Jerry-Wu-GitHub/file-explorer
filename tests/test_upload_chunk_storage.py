"""LocalUploadChunkStorage 单元测试。

覆盖分片写入、大小校验、列表、删除、合并、空文件、清理与磁盘空间
查询。合并与清理的失败路径也在此覆盖。
"""

import io
import threading
from pathlib import Path

import pytest

from app.constants import CHUNK_FILE_SUFFIX, MERGE_TEMP_SUFFIX
from app.errors import BusinessError, ErrorCode
from app.storage.upload_chunk_storage import LocalUploadChunkStorage
from app.storage.upload_lock_manager import UploadLockManager


def build_storage(tmp_path: Path) -> LocalUploadChunkStorage:
    """构造使用临时目录的分片存储。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        配置好的分片存储。
    """
    return LocalUploadChunkStorage(tmp_path / "temp")


def test_write_chunk_creates_file(tmp_path: Path) -> None:
    """写入分片应生成对应文件并返回写入字节数。"""
    storage = build_storage(tmp_path)
    written = storage.write_chunk(
        "u1", 0, io.BytesIO(b"hello"), expected_size=5
    )
    assert written == 5
    assert storage.chunk_path("u1", 0).read_bytes() == b"hello"


def test_write_chunk_rejects_size_mismatch(tmp_path: Path) -> None:
    """写入字节数与期望不符时抛出 ``INVALID_CHUNK_SIZE``。"""
    storage = build_storage(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        storage.write_chunk("u1", 0, io.BytesIO(b"hello"), expected_size=10)
    assert exc_info.value.code == ErrorCode.INVALID_CHUNK_SIZE
    assert not storage.chunk_path("u1", 0).exists()


def test_write_chunk_removes_temp_on_mismatch(tmp_path: Path) -> None:
    """大小校验失败后不应残留临时文件。"""
    storage = build_storage(tmp_path)
    with pytest.raises(BusinessError):
        storage.write_chunk("u1", 0, io.BytesIO(b"hi"), expected_size=100)
    chunks_dir = storage.chunks_directory("u1")
    leftovers = [
        entry
        for entry in chunks_dir.iterdir()
        if entry.name.endswith(".tmp")
    ]
    assert leftovers == []


def test_write_chunk_overwrites_same_number(tmp_path: Path) -> None:
    """重复写入同一分片应以最后一次为准。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 0, io.BytesIO(b"first"), expected_size=5)
    storage.write_chunk("u1", 0, io.BytesIO(b"second"), expected_size=6)
    assert storage.chunk_path("u1", 0).read_bytes() == b"second"


def test_chunk_size_on_disk_missing(tmp_path: Path) -> None:
    """分片不存在时返回 ``None``。"""
    storage = build_storage(tmp_path)
    assert storage.chunk_size_on_disk("u1", 0) is None


def test_chunk_size_on_disk_present(tmp_path: Path) -> None:
    """分片存在时返回其字节数。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 0, io.BytesIO(b"hello"), expected_size=5)
    assert storage.chunk_size_on_disk("u1", 0) == 5


def test_list_uploaded_chunks_empty(tmp_path: Path) -> None:
    """无分片时返回空列表。"""
    storage = build_storage(tmp_path)
    assert storage.list_uploaded_chunks("u1") == []


def test_list_uploaded_chunks_sorted(tmp_path: Path) -> None:
    """分片编号按升序返回，忽略临时文件。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 2, io.BytesIO(b"cc"), expected_size=2)
    storage.write_chunk("u1", 0, io.BytesIO(b"a"), expected_size=1)
    storage.write_chunk("u1", 1, io.BytesIO(b"bb"), expected_size=2)
    assert storage.list_uploaded_chunks("u1") == [0, 1, 2]


def test_remove_chunk(tmp_path: Path) -> None:
    """删除分片后文件消失。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 0, io.BytesIO(b"hello"), expected_size=5)
    storage.remove_chunk("u1", 0)
    assert not storage.chunk_path("u1", 0).exists()


def test_remove_chunk_is_idempotent(tmp_path: Path) -> None:
    """删除不存在的分片不抛异常。"""
    storage = build_storage(tmp_path)
    storage.remove_chunk("u1", 0)


def test_merge_chunks_in_order(tmp_path: Path) -> None:
    """合并后目标文件内容与分片顺序一致。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 0, io.BytesIO(b"hello "), expected_size=6)
    storage.write_chunk("u1", 1, io.BytesIO(b"world"), expected_size=5)
    target = tmp_path / "out.bin"
    storage.merge_chunks("u1", 2, target)
    assert target.read_bytes() == b"hello world"


def test_merge_chunks_empty_file(tmp_path: Path) -> None:
    """``total_chunks=0`` 时生成空文件。"""
    storage = build_storage(tmp_path)
    target = tmp_path / "empty.bin"
    storage.merge_chunks("u1", 0, target)
    assert target.is_file()
    assert target.read_bytes() == b""


def test_merge_chunks_rejects_missing_chunk(tmp_path: Path) -> None:
    """分片缺失时抛出 ``UPLOAD_INCOMPLETE``。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 0, io.BytesIO(b"a"), expected_size=1)
    target = tmp_path / "out.bin"
    with pytest.raises(BusinessError) as exc_info:
        storage.merge_chunks("u1", 2, target)
    assert exc_info.value.code == ErrorCode.UPLOAD_INCOMPLETE
    assert not target.exists()


def test_merge_chunks_does_not_leave_temp_on_failure(
    tmp_path: Path,
) -> None:
    """合并失败后不应残留合并临时文件。"""
    storage = build_storage(tmp_path)
    with pytest.raises(BusinessError):
        storage.merge_chunks("u1", 1, tmp_path / "out.bin")
    leftovers = [
        entry
        for entry in tmp_path.iterdir()
        if entry.name.endswith(MERGE_TEMP_SUFFIX)
    ]
    assert leftovers == []


def test_merge_chunks_replaces_existing_target(tmp_path: Path) -> None:
    """合并应原子替换已存在的目标文件。"""
    storage = build_storage(tmp_path)
    target = tmp_path / "out.bin"
    target.write_bytes(b"old")
    storage.write_chunk("u1", 0, io.BytesIO(b"new"), expected_size=3)
    storage.merge_chunks("u1", 1, target)
    assert target.read_bytes() == b"new"


def test_merge_chunks_creates_parent_directory(tmp_path: Path) -> None:
    """目标父目录不存在时应自动创建。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 0, io.BytesIO(b"x"), expected_size=1)
    target = tmp_path / "nested" / "deeper" / "out.bin"
    storage.merge_chunks("u1", 1, target)
    assert target.read_bytes() == b"x"


def test_cleanup_session_removes_directory(tmp_path: Path) -> None:
    """清理会话后该会话目录消失。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 0, io.BytesIO(b"a"), expected_size=1)
    storage.write_chunk("u1", 1, io.BytesIO(b"b"), expected_size=1)
    storage.cleanup_session("u1")
    assert not storage.session_root("u1").exists()


def test_cleanup_session_is_idempotent(tmp_path: Path) -> None:
    """清理不存在的会话不抛异常。"""
    storage = build_storage(tmp_path)
    storage.cleanup_session("nonexistent")


def test_available_disk_space_positive(tmp_path: Path) -> None:
    """磁盘可用空间查询应返回正数。"""
    storage = build_storage(tmp_path)
    assert storage.available_disk_space_bytes() > 0


def test_chunk_file_suffix_used(tmp_path: Path) -> None:
    """分片文件名使用常量后缀。"""
    storage = build_storage(tmp_path)
    storage.write_chunk("u1", 5, io.BytesIO(b"x"), expected_size=1)
    assert storage.chunk_path("u1", 5).name == f"5{CHUNK_FILE_SUFFIX}"


def test_concurrent_chunk_write_with_lock(tmp_path: Path) -> None:
    """分片级锁保证同一分片并发写入后结果为最后一个完整写入。"""
    storage = build_storage(tmp_path)
    locks = UploadLockManager(tmp_path / "locks")
    barrier = threading.Barrier(4)
    payloads = [bytes([index]) * 100 for index in range(4)]

    def worker(index: int) -> None:
        barrier.wait()
        with locks.chunk_lock("u1", 0):
            storage.write_chunk(
                "u1", 0, io.BytesIO(payloads[index]), expected_size=100
            )

    threads = [
        threading.Thread(target=worker, args=(index,)) for index in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    final = storage.chunk_path("u1", 0).read_bytes()
    assert len(final) == 100
    assert len(set(final)) == 1
    assert final in payloads


def test_concurrent_different_chunks_do_not_conflict(
    tmp_path: Path,
) -> None:
    """不同分片可并发写入，结果均完整。"""
    storage = build_storage(tmp_path)
    locks = UploadLockManager(tmp_path / "locks")
    barrier = threading.Barrier(4)

    def worker(chunk_number: int) -> None:
        payload = bytes([chunk_number]) * 50
        barrier.wait()
        with locks.chunk_lock("u1", chunk_number):
            storage.write_chunk(
                "u1", chunk_number, io.BytesIO(payload), expected_size=50
            )

    threads = [
        threading.Thread(target=worker, args=(index,)) for index in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert storage.list_uploaded_chunks("u1") == [0, 1, 2, 3]
    for chunk_number in range(4):
        content = storage.chunk_path("u1", chunk_number).read_bytes()
        assert content == bytes([chunk_number]) * 50
