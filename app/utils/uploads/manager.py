"""分片上传会话管理：状态机、分片写入、合并完成、取消。"""

import hashlib
import math
import os
import posixpath
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from app.config import get_config
from app.constants.uploads import (
    MERGE_BUFFER_SIZE,
    UPLOAD_STATUS_CANCELED,
    UPLOAD_STATUS_COMPLETED,
    UPLOAD_STATUS_COMPLETING,
    UPLOAD_STATUS_CREATED,
    UPLOAD_STATUS_EXPIRED,
    UPLOAD_STATUS_UPLOADING,
)
from app.models.fs_entry import FsEntry
from app.models.upload_session import UploadSession
from app.utils.errors import (
    FileExplorerError,
    ChecksumMismatchError,
    InsufficientStorageError,
    ParentNotFoundError,
    PayloadTooLargeError,
    UploadConflictError,
    UploadExpiredError,
    UploadNotFoundError,
    ValidationFailedError,
)
from app.utils.fs_utils import build_entry
from app.utils.path_utils import resolve_path, validate_relative_path
from app.utils.uploads import chunk_store, session_store

_UNFINISHED_STATUSES: frozenset[str] = frozenset(
    {UPLOAD_STATUS_CREATED, UPLOAD_STATUS_UPLOADING, UPLOAD_STATUS_COMPLETING}
)


def create_upload_session(
    virtual_path: str,
    size: int,
    chunk_size: int,
    overwrite: bool,
    checksum_algorithm: Optional[str],
    checksum_value: Optional[str],
) -> UploadSession:
    """初始化分片上传会话。"""
    config = get_config()

    normalized: str = _validate_target_path(virtual_path)
    _validate_checksum_pair(checksum_algorithm, checksum_value, required=False)
    _validate_size(size, config.max_upload_size)

    chunk_size = _normalize_chunk_size(chunk_size, config)
    total_chunks: int = math.ceil(size / chunk_size) if size > 0 else 0
    if total_chunks > config.max_chunks:
        raise ValidationFailedError(
            "分片大小过小导致分片数量超限", {"maxChunks": config.max_chunks}
        )

    parent_virtual: str = posixpath.dirname(normalized)
    parent_path: Path = _resolve_parent_path(parent_virtual)
    entry_name: str = posixpath.basename(normalized)
    _check_target_conflict(parent_path / entry_name, overwrite)

    session_store.ensure_upload_dirs()
    _check_concurrent_limit(config.max_concurrent_uploads)
    _check_storage_for_size(size)

    now: float = time.time()
    upload_id: str = str(uuid.uuid4())
    session: UploadSession = UploadSession(
        upload_id=upload_id,
        path=normalized,
        size=size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        uploaded_chunks=[],
        uploaded_bytes=0,
        status=UPLOAD_STATUS_CREATED,
        overwrite=overwrite,
        checksum_algorithm=checksum_algorithm,
        checksum_value=checksum_value,
        created_at=now,
        updated_at=now,
        expires_at=now + config.upload_session_ttl_seconds,
    )
    session_store.save_session(session)
    session_store.chunk_dir_path(upload_id).mkdir(parents=True, exist_ok=True)
    return session


def query_upload_session(upload_id: str) -> UploadSession:
    """查询上传状态（断点续传），自动标记过期会话。"""
    with session_store.SessionLock(upload_id):
        session: UploadSession = _load_unexpired_session(upload_id)
    return session


def upload_chunk(
    upload_id: str,
    chunk_number: int,
    content: bytes,
    content_md5: Optional[str],
    chunk_sha256: Optional[str],
) -> UploadSession:
    """上传单个分片，重复上传按幂等处理（最后写入生效）。"""
    with session_store.SessionLock(upload_id):
        session: UploadSession = _load_unexpired_session(upload_id)
        _assert_uploading_allowed(session)

        if chunk_number < 0 or chunk_number >= session.total_chunks:
            raise UploadConflictError(416, "CHUNK_OUT_OF_RANGE", "分片编号越界")

        expected_size: int = _expected_chunk_size(session, chunk_number)
        if len(content) != expected_size:
            raise UploadConflictError(400, "INVALID_CHUNK_SIZE", "分片大小不符合预期")

        chunk_store.verify_chunk_checksum(content, content_md5, chunk_sha256)
        chunk_store.write_chunk(upload_id, chunk_number, content)

        was_uploaded: bool = chunk_number in session.uploaded_chunks
        session.uploaded_chunks = sorted(set(session.uploaded_chunks) | {chunk_number})
        if not was_uploaded:
            session.uploaded_bytes += len(content)
        session.status = UPLOAD_STATUS_UPLOADING
        session.updated_at = time.time()
        session_store.save_session(session)
    return session


def complete_upload(
    upload_id: str,
    checksum_algorithm: Optional[str],
    checksum_value: Optional[str],
) -> tuple[UploadSession, FsEntry, bool]:
    """完成上传并合并分片，返回（会话, 最终文件元数据, 是否原本已完成）。

    原本已完成时直接返回现有文件元数据，保证客户端重试安全。
    """
    _validate_checksum_pair(checksum_algorithm, checksum_value, required=False)

    with session_store.SessionLock(upload_id):
        session: UploadSession = _load_unexpired_session(upload_id)

        if session.status == UPLOAD_STATUS_COMPLETED:
            return session, _build_final_entry(session), True
        if session.status == UPLOAD_STATUS_COMPLETING:
            raise UploadConflictError(409, "UPLOAD_COMPLETING", "上传正在合并")
        if session.status == UPLOAD_STATUS_CANCELED:
            raise UploadConflictError(409, "UPLOAD_CANCELED", "上传已取消")

        missing_chunks: list[int] = _missing_chunks(session)
        if missing_chunks:
            raise UploadConflictError(
                409, "UPLOAD_INCOMPLETE", "分片未全部上传", {"missingChunks": missing_chunks}
            )

        session.status = UPLOAD_STATUS_COMPLETING
        session.updated_at = time.time()
        session_store.save_session(session)

        try:
            final_entry: FsEntry = _merge_chunks(session, checksum_algorithm, checksum_value)
            session.status = UPLOAD_STATUS_COMPLETED
            session.updated_at = time.time()
            session_store.save_session(session)
        except (ChecksumMismatchError, FileExplorerError):
            session.status = UPLOAD_STATUS_UPLOADING
            session.updated_at = time.time()
            session_store.save_session(session)
            raise

        session_store.delete_chunk_dir(upload_id)
    return session, final_entry, False


def cancel_upload(upload_id: str) -> None:
    """取消上传并清理分片；对不存在或已过期会话保持幂等。"""
    try:
        with session_store.SessionLock(upload_id):
            session: UploadSession = _load_unexpired_session(upload_id)
            if session.status == UPLOAD_STATUS_COMPLETED:
                raise UploadConflictError(409, "UPLOAD_ALREADY_COMPLETED", "上传已完成")
            if session.status == UPLOAD_STATUS_COMPLETING:
                raise UploadConflictError(409, "UPLOAD_COMPLETING", "上传正在合并")
            if session.status == UPLOAD_STATUS_CANCELED:
                return

            session_store.delete_chunk_dir(upload_id)
            session.status = UPLOAD_STATUS_CANCELED
            session.updated_at = time.time()
            session_store.save_session(session)
    except UploadNotFoundError:
        return
    except UploadExpiredError:
        return


def _load_unexpired_session(upload_id: str) -> UploadSession:
    """读取会话并处理过期：已过期会话标记为 expired 并抛出 410。"""
    session: UploadSession = session_store.load_session(upload_id)
    if time.time() > session.expires_at and session.status in _UNFINISHED_STATUSES:
        session.status = UPLOAD_STATUS_EXPIRED
        session.updated_at = time.time()
        session_store.save_session(session)
        raise UploadExpiredError("上传会话已过期")
    return session


def _assert_uploading_allowed(session: UploadSession) -> None:
    """检查会话是否仍允许上传分片。"""
    if session.status == UPLOAD_STATUS_COMPLETED:
        raise UploadConflictError(409, "UPLOAD_ALREADY_COMPLETED", "上传已完成")
    if session.status == UPLOAD_STATUS_COMPLETING:
        raise UploadConflictError(409, "UPLOAD_COMPLETING", "上传正在合并")
    if session.status == UPLOAD_STATUS_CANCELED:
        raise UploadConflictError(409, "UPLOAD_CANCELED", "上传已取消")


def _validate_target_path(virtual_path: str) -> str:
    """校验目标路径：规范、非根、含文件名。"""
    normalized: str = validate_relative_path(virtual_path)
    if normalized == "/":
        raise ValidationFailedError("目标路径必须包含文件名")
    entry_name: str = posixpath.basename(normalized)
    if not entry_name or entry_name in (".", ".."):
        raise ValidationFailedError("目标路径必须包含文件名")
    return normalized


def _resolve_parent_path(parent_virtual: str) -> Path:
    """解析父目录真实路径，不存在时抛出 404。"""
    parent_path: Path = resolve_path(
        parent_virtual, follow_link=True, outside_code="PATH_OUTSIDE_SANDBOX"
    )
    if not os.path.isdir(parent_path):
        raise ParentNotFoundError("父目录不存在")
    return parent_path


def _check_target_conflict(target: Path, overwrite: bool) -> None:
    """检查目标是否已存在；目录即使允许覆盖也拒绝。"""
    if not os.path.lexists(target):
        return
    if os.path.isdir(target) and not os.path.islink(target):
        raise UploadConflictError(409, "FILE_EXISTS", "目标已存在且为目录")
    if not overwrite:
        raise UploadConflictError(409, "FILE_EXISTS", "目标文件已存在")


def _validate_size(size: int, max_size: int) -> None:
    """校验文件总大小。"""
    if size < 0:
        raise ValidationFailedError("size 必须大于等于 0")
    if size > max_size:
        raise PayloadTooLargeError(f"文件大小超过限制 {max_size}")


def _normalize_chunk_size(chunk_size: int, config) -> int:
    """规范化分片大小：默认值兜底 + 范围校验。"""
    if chunk_size is None:
        chunk_size = config.default_chunk_size
    if chunk_size < config.min_chunk_size or chunk_size > config.max_chunk_size:
        raise ValidationFailedError(
            "分片大小超出允许范围",
            {"minChunkSize": config.min_chunk_size, "maxChunkSize": config.max_chunk_size},
        )
    return chunk_size


def _validate_checksum_pair(
    algorithm: Optional[str], value: Optional[str], *, required: bool
) -> None:
    """校验整体校验值字段的组合合法性。"""
    if algorithm is None and value is None:
        if required:
            raise ValidationFailedError("缺少整体校验信息")
        return
    if algorithm is None or value is None:
        raise ValidationFailedError("checksum 必须同时提供 algorithm 与 value")
    if not value:
        raise ValidationFailedError("checksum.value 不能为空")
    try:
        hashlib.new(algorithm.lower())
    except ValueError as exc:
        raise ValidationFailedError(f"不支持的校验算法: {algorithm}") from exc


def _check_concurrent_limit(max_concurrent: int) -> None:
    """检查活动会话数是否超过并发上限。"""
    active_count: int = 0
    for upload_id in session_store.list_session_ids():
        try:
            session: UploadSession = session_store.load_session(upload_id)
        except UploadNotFoundError:
            continue
        if session.status in _UNFINISHED_STATUSES and session.expires_at > time.time():
            active_count += 1
    if active_count >= max_concurrent:
        raise UploadConflictError(429, "TOO_MANY_UPLOADS", "并发上传会话数超限")


def _check_storage_for_size(size: int) -> None:
    """初始化时检查磁盘剩余空间。"""
    disk_usage = shutil.disk_usage(str(session_store.upload_root_path()))
    if disk_usage.free < size:
        raise InsufficientStorageError("磁盘剩余空间不足")


def _expected_chunk_size(session: UploadSession, chunk_number: int) -> int:
    """计算指定分片的预期大小。"""
    if chunk_number < session.total_chunks - 1:
        return session.chunk_size
    return session.size - session.chunk_size * (session.total_chunks - 1)


def _missing_chunks(session: UploadSession) -> list[int]:
    """返回缺失分片编号列表。"""
    uploaded_set: set[int] = set(session.uploaded_chunks)
    return [number for number in range(session.total_chunks) if number not in uploaded_set]


def _merge_chunks(
    session: UploadSession,
    checksum_algorithm: Optional[str],
    checksum_value: Optional[str],
) -> FsEntry:
    """按编号升序合并分片，校验整体校验值后原子替换目标文件。"""
    parent_virtual: str = posixpath.dirname(session.path)
    parent_path: Path = _resolve_parent_path(parent_virtual)
    entry_name: str = posixpath.basename(session.path)
    target_path: Path = parent_path / entry_name

    _check_target_conflict(target_path, session.overwrite)
    _check_storage_for_size(session.size)

    temp_path: Path = parent_path / f".{entry_name}.upload-{session.upload_id}.tmp"
    try:
        with open(temp_path, "wb") as output_handle:
            for chunk_path in chunk_store.iter_chunk_paths(session.upload_id, session.total_chunks):
                with open(chunk_path, "rb") as input_handle:
                    shutil.copyfileobj(input_handle, output_handle, MERGE_BUFFER_SIZE)
            output_handle.flush()
            os.fsync(output_handle.fileno())

        _verify_merged_checksum(temp_path, checksum_algorithm, checksum_value)
        os.replace(temp_path, target_path)
        _fsync_directory(parent_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    return build_entry(target_path, session.path, follow_link=True)


def _verify_merged_checksum(
    temp_path: Path,
    checksum_algorithm: Optional[str],
    checksum_value: Optional[str],
) -> None:
    """合并完成后校验整体校验值（以本次传入为准）。"""
    if checksum_algorithm is None:
        return
    digest = hashlib.new(checksum_algorithm.lower())
    with open(temp_path, "rb") as file_handle:
        while True:
            block: bytes = file_handle.read(MERGE_BUFFER_SIZE)
            if not block:
                break
            digest.update(block)
    if digest.hexdigest() != checksum_value.lower():
        raise ChecksumMismatchError("整体校验值不匹配")


def _fsync_directory(directory: Path) -> None:
    """同步目录元数据，确保重命名结果落盘。"""
    directory_descriptor: int = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _build_final_entry(session: UploadSession) -> FsEntry:
    """为已完成会话重建最终文件元数据。"""
    return build_final_entry(session.path)


def build_final_entry(virtual_path: str) -> FsEntry:
    """根据目标虚拟路径重建最终文件元数据（查询已完成会话时使用）。"""
    target_path: Path = resolve_path(
        virtual_path, follow_link=True, outside_code="PATH_OUTSIDE_SANDBOX"
    )
    if not os.path.lexists(target_path):
        raise UploadConflictError(404, "NOT_FOUND", "最终文件已不存在")
    return build_entry(target_path, virtual_path, follow_link=True)

