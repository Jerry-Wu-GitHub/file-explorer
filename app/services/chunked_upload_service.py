"""分片上传服务。

本模块提供 :class:`ChunkedUploadService`，负责分片上传会话的生命
周期管理。当前实现覆盖初始化与状态查询两个操作；分片上传、完成
与取消将在后续迭代中追加。

所有路径都经过 :class:`app.services.path_service.PathService` 校验；
分片文件由 :class:`app.storage.upload_chunk_storage.LocalUploadChunkStorage`
管理；跨进程互斥由 :class:`app.storage.upload_lock_manager.UploadLockManager`
提供；会话元数据持久化到
:class:`app.repositories.upload_session_repository.UploadSessionRepository`。
"""

import hashlib
import time
import uuid
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Optional

from ..config import Config
from ..constants import (
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_COMPLETING,
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_UPLOADING,
    UPLOAD_STORAGE_SAFETY_MARGIN_BYTES,
)
from ..errors import BusinessError, ErrorCode
from ..models.upload_session import (
    UploadChunkRecord,
    UploadSession,
    UploadSessionSnapshot,
)
from ..repositories.upload_session_repository import (
    UploadSessionRepository,
)
from ..schemas.upload import (
    ChecksumSchema,
    CompleteUploadRequest,
    InitializeUploadRequest,
    UploadChunkResponse,
    UploadSessionResponse,
)
from ..schemas.filesystem import FileSystemEntryMetadata
from ..storage.upload_chunk_storage import LocalUploadChunkStorage
from ..storage.upload_lock_manager import UploadLockManager
from .metadata_service import MetadataService
from .path_service import PathService


EXPIRY_ELIGIBLE_STATUSES: tuple[str, ...] = (STATUS_CREATED, STATUS_UPLOADING)
"""允许因超时被标记为 ``expired`` 的会话状态。"""

CHUNK_READ_BUFFER_SIZE: int = 1024 * 1024
"""从上传流读取内容时的块大小（字节）。"""

CHUNK_MEMORY_BUFFER_SIZE: int = 8 * 1024 * 1024
"""分片校验缓冲使用的内存上限（字节），超过后溢出到磁盘。"""

UPLOADABLE_STATUSES: tuple[str, ...] = (STATUS_CREATED, STATUS_UPLOADING)
"""允许上传分片的状态集合。"""


class ChunkedUploadService:
    """分片上传的会话管理服务。

    Attributes:
        path_service: 沙箱路径解析服务。
        metadata_service: 元数据组装服务。
        repository: 上传会话仓储。
        storage: 分片文件存储。
        lock_manager: 跨进程锁管理器。
        config: 项目全局配置。
    """

    def __init__(
        self,
        path_service: PathService,
        metadata_service: MetadataService,
        repository: UploadSessionRepository,
        storage: LocalUploadChunkStorage,
        lock_manager: UploadLockManager,
        config: Config,
    ) -> None:
        """构造分片上传服务。

        Args:
            path_service: 沙箱路径解析服务。
            metadata_service: 元数据组装服务。
            repository: 上传会话仓储。
            storage: 分片文件存储。
            lock_manager: 跨进程锁管理器。
            config: 项目全局配置。
        """
        self._path_service: PathService = path_service
        self._metadata_service: MetadataService = metadata_service
        self._repository: UploadSessionRepository = repository
        self._storage: LocalUploadChunkStorage = storage
        self._lock_manager: UploadLockManager = lock_manager
        self._config: Config = config

    def initialize_upload(
        self,
        request: InitializeUploadRequest,
    ) -> UploadSessionResponse:
        """初始化一个分片上传会话。

        初始化过程不会创建目标文件，只创建会话记录与分片临时目录。

        Args:
            request: 初始化请求。

        Returns:
            新会话的状态响应。

        Raises:
            BusinessError: 路径非法、父目录缺失、目标冲突、参数越界
                或磁盘空间不足。
        """
        if request.path.endswith("/"):
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                "目标路径不能以 / 结尾，必须包含文件名",
            )

        target_real = self._path_service.resolve_real_path(
            request.path, follow_link=False
        )
        self._path_service.ensure_parent_exists(target_real)
        self._verify_target_for_new_upload(target_real, request.overwrite)
        self._verify_size(request.size)

        chunk_size = self._resolve_chunk_size(request.chunk_size)
        total_chunks = self._compute_total_chunks(request.size, chunk_size)
        self._verify_total_chunks(total_chunks)
        self._verify_concurrent_sessions()
        self._verify_disk_space(request.size)

        upload_id = uuid.uuid4().hex
        now = time.time()
        expires_at = now + self._config.upload_session_ttl_seconds
        session = UploadSession(
            upload_id=upload_id,
            target_path=self._path_service.to_virtual_path(target_real),
            size=request.size,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            overwrite=request.overwrite,
            checksum_algorithm=(
                request.checksum.algorithm if request.checksum else None
            ),
            checksum_value=(
                request.checksum.value if request.checksum else None
            ),
            status=STATUS_CREATED,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        self._persist_session(session)
        return self._build_response(
            UploadSessionSnapshot(
                session=session,
                uploaded_chunks=[],
                uploaded_bytes=0,
            )
        )

    def get_upload_status(self, upload_id: str) -> UploadSessionResponse:
        """查询上传会话状态，用于断点续传。

        Args:
            upload_id: 上传会话 ID。

        Returns:
            会话状态响应。已完成 / 已取消的会话也会正常返回，
            仅已过期的会话返回 ``UPLOAD_EXPIRED``。

        Raises:
            BusinessError: 会话不存在或已过期。
        """
        session = self._load_session_or_raise(upload_id)
        session = self._apply_expiry_if_needed(session)
        if session.status == STATUS_EXPIRED:
            raise BusinessError(
                ErrorCode.UPLOAD_EXPIRED,
                f"上传会话已过期：{upload_id}",
            )
        snapshot = self._repository.get_snapshot(upload_id)
        if snapshot is None:
            raise BusinessError(
                ErrorCode.UPLOAD_NOT_FOUND,
                f"上传会话不存在：{upload_id}",
            )
        return self._build_response(snapshot)

    def _verify_target_for_new_upload(
        self,
        target_real: Path,
        overwrite: bool,
    ) -> None:
        """校验目标路径是否可作为新的上传目标。

        Args:
            target_real: 目标文件的真实路径。
            overwrite: 是否允许覆盖。

        Raises:
            BusinessError: 目标是目录，或目标已存在且不允许覆盖。
        """
        if target_real.is_dir():
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标已存在且为目录：{target_real.name}",
            )
        exists = target_real.exists() or target_real.is_symlink()
        if exists and not overwrite:
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标文件已存在：{target_real.name}",
            )

    def _verify_size(self, size: int) -> None:
        """校验文件总大小是否超过上限。

        Args:
            size: 文件总字节数。

        Raises:
            BusinessError: 超过 ``max_upload_size``。
        """
        if size > self._config.max_upload_size:
            raise BusinessError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                f"文件大小超过上限：{self._config.max_upload_size} 字节",
            )

    def _resolve_chunk_size(self, requested: int | None) -> int:
        """确定本次会话使用的分片大小。

        Args:
            requested: 客户端指定的分片大小，可为 ``None``。

        Returns:
            通过校验的分片大小。

        Raises:
            BusinessError: 分片大小超出配置范围。
        """
        chunk_size = (
            requested
            if requested is not None
            else self._config.default_chunk_size
        )
        if (
            chunk_size < self._config.min_chunk_size
            or chunk_size > self._config.max_chunk_size
        ):
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                (
                    f"分片大小必须在 {self._config.min_chunk_size} 与 "
                    f"{self._config.max_chunk_size} 字节之间：{chunk_size}"
                ),
            )
        return chunk_size

    def _compute_total_chunks(self, size: int, chunk_size: int) -> int:
        """计算分片总数。

        ``size == 0`` 时返回 0，与服务端「空文件无需上传分片」的
        约定一致。

        Args:
            size: 文件总字节数。
            chunk_size: 分片大小。

        Returns:
            分片总数。
        """
        if size == 0:
            return 0
        return (size + chunk_size - 1) // chunk_size

    def _verify_total_chunks(self, total_chunks: int) -> None:
        """校验分片总数是否超过上限。

        Args:
            total_chunks: 分片总数。

        Raises:
            BusinessError: 超过 ``max_chunks``。
        """
        if total_chunks > self._config.max_chunks:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                (
                    f"分片数量超过上限：{total_chunks} > "
                    f"{self._config.max_chunks}，请增大 chunkSize"
                ),
            )

    def _verify_concurrent_sessions(self) -> None:
        """校验当前活动会话数是否超过上限。

        Raises:
            BusinessError: 活动会话数达到上限。
        """
        active_count = self._repository.count_active_sessions()
        if active_count >= self._config.max_concurrent_upload_sessions:
            raise BusinessError(
                ErrorCode.CONFLICT,
                (
                    "并发上传会话数已达上限："
                    f"{self._config.max_concurrent_upload_sessions}"
                ),
            )

    def _verify_disk_space(self, size: int) -> None:
        """校验磁盘剩余空间是否足够。

        Args:
            size: 文件总字节数。

        Raises:
            BusinessError: 剩余空间不足。
        """
        required = size + UPLOAD_STORAGE_SAFETY_MARGIN_BYTES
        available = self._storage.available_disk_space_bytes()
        if available < required:
            raise BusinessError(
                ErrorCode.INSUFFICIENT_STORAGE,
                f"磁盘空间不足：需要 {required} 字节，可用 {available} 字节",
            )

    def _persist_session(self, session: UploadSession) -> None:
        """创建临时目录并持久化会话。

        写入数据库失败时会尝试清理已创建的临时目录，避免残留。

        Args:
            session: 会话对象。
        """
        self._storage.ensure_session_directory(session.upload_id)
        try:
            self._repository.create_session(session)
        except BusinessError:
            self._storage.cleanup_session(session.upload_id)
            raise

    def _load_session_or_raise(self, upload_id: str) -> UploadSession:
        """按 ID 读取会话，不存在时抛出 ``UPLOAD_NOT_FOUND``。

        Args:
            upload_id: 上传会话 ID。

        Returns:
            会话对象。

        Raises:
            BusinessError: 会话不存在。
        """
        session = self._repository.get_session(upload_id)
        if session is None:
            raise BusinessError(
                ErrorCode.UPLOAD_NOT_FOUND,
                f"上传会话不存在：{upload_id}",
            )
        return session

    def _apply_expiry_if_needed(
        self,
        session: UploadSession,
    ) -> UploadSession:
        """在读取会话时按需将其标记为过期。

        仅对 ``created`` / ``uploading`` 状态的会话生效；一旦标记
        成功，顺手清理分片临时文件。

        Args:
            session: 会话对象。

        Returns:
            处理后的会话对象。
        """
        if session.status not in EXPIRY_ELIGIBLE_STATUSES:
            return session
        now = time.time()
        if session.expires_at >= now:
            return session

        transitioned = self._repository.transition_status(
            session.upload_id,
            EXPIRY_ELIGIBLE_STATUSES,
            STATUS_EXPIRED,
            now,
        )
        if transitioned:
            self._storage.cleanup_session(session.upload_id)
        reloaded = self._repository.get_session(session.upload_id)
        return reloaded if reloaded is not None else session

    def _build_response(
        self,
        snapshot: UploadSessionSnapshot,
    ) -> UploadSessionResponse:
        """将快照转换为对外响应。

        Args:
            snapshot: 会话快照。

        Returns:
            会话状态响应。
        """
        session = snapshot.session
        return UploadSessionResponse(
            upload_id=session.upload_id,
            path=session.target_path,
            size=session.size,
            chunk_size=session.chunk_size,
            total_chunks=session.total_chunks,
            uploaded_chunks=snapshot.uploaded_chunks,
            missing_chunks=snapshot.missing_chunks,
            uploaded_bytes=snapshot.uploaded_bytes,
            status=session.status,  # type: ignore[arg-type]
            created_at=session.created_at,
            updated_at=session.updated_at,
            expires_at=session.expires_at,
        )


    def upload_chunk(
        self,
        upload_id: str,
        chunk_number: int,
        content: BinaryIO,
        content_md5: Optional[str] = None,
        chunk_sha256: Optional[str] = None,
    ) -> UploadChunkResponse:
        """上传单个分片。

        允许乱序与并发上传；同一分片的并发上传通过分片级锁串行化。
        若客户端提供了校验值，则在写入前完成校验，校验失败不会
        保存任何数据。

        Args:
            upload_id: 上传会话 ID。
            chunk_number: 分片编号，从 0 开始。
            content: 分片内容流，需支持 ``read`` 方法。
            content_md5: 可选的 MD5 十六进制字符串，来自
                ``Content-MD5`` 请求头。
            chunk_sha256: 可选的 SHA-256 十六进制字符串，来自
                ``X-Chunk-SHA256`` 请求头。

        Returns:
            分片上传结果。

        Raises:
            BusinessError: 会话不存在、已过期、不可上传、分片编号
                越界、大小不符或校验失败。
        """
        with self._lock_manager.session_read_lock(upload_id):
            session = self._load_session_or_raise(upload_id)
            session = self._apply_expiry_if_needed(session)
            self._verify_session_uploadable(session)
            self._verify_chunk_number(session, chunk_number)
            expected_size = self._compute_expected_chunk_size(
                session, chunk_number
            )

            received_size = self._write_chunk_safely(
                session,
                chunk_number,
                expected_size,
                content,
                content_md5,
                chunk_sha256,
            )

            self._repository.transition_status(
                upload_id,
                (STATUS_CREATED,),
                STATUS_UPLOADING,
                time.time(),
            )

            snapshot = self._repository.get_snapshot(upload_id)
            if snapshot is None:
                raise BusinessError(
                    ErrorCode.UPLOAD_NOT_FOUND,
                    f"上传会话不存在：{upload_id}",
                )
            return self._build_chunk_response(
                snapshot, chunk_number, received_size
            )

    def _write_chunk_safely(
        self,
        session: UploadSession,
        chunk_number: int,
        expected_size: int,
        content: BinaryIO,
        content_md5: Optional[str],
        chunk_sha256: Optional[str],
    ) -> int:
        """缓冲内容、校验校验和与大小，然后写入存储。

        Args:
            session: 会话对象。
            chunk_number: 分片编号。
            expected_size: 期望字节数。
            content: 分片内容流。
            content_md5: 可选的 MD5 十六进制值。
            chunk_sha256: 可选的 SHA-256 十六进制值。

        Returns:
            实际写入的字节数。

        Raises:
            BusinessError: 大小不符、校验失败或写入失败。
        """
        with SpooledTemporaryFile(
            max_size=CHUNK_MEMORY_BUFFER_SIZE, suffix=".chunk"
        ) as buffer:
            received_size, md5_hex, sha256_hex = self._buffer_and_hash(
                content, buffer
            )
            self._verify_chunk_checksum(
                content_md5, chunk_sha256, md5_hex, sha256_hex
            )
            if received_size != expected_size:
                raise BusinessError(
                    ErrorCode.INVALID_CHUNK_SIZE,
                    (
                        f"分片 {chunk_number} 实际大小 {received_size} 字节，"
                        f"预期 {expected_size} 字节"
                    ),
                )
            buffer.seek(0)
            with self._lock_manager.chunk_lock(
                session.upload_id, chunk_number
            ):
                self._storage.write_chunk(
                    session.upload_id,
                    chunk_number,
                    buffer,
                    expected_size,
                )
                self._repository.record_chunk(
                    UploadChunkRecord(
                        upload_id=session.upload_id,
                        chunk_number=chunk_number,
                        received_size=received_size,
                        updated_at=time.time(),
                    )
                )
        return received_size

    def _verify_session_uploadable(self, session: UploadSession) -> None:
        """校验会话当前允许上传分片。

        Args:
            session: 会话对象。

        Raises:
            BusinessError: 会话处于不可上传的状态。
        """
        status = session.status
        if status == STATUS_COMPLETING:
            raise BusinessError(
                ErrorCode.UPLOAD_COMPLETING,
                "上传正在合并，拒绝新的分片",
            )
        if status == STATUS_COMPLETED:
            raise BusinessError(
                ErrorCode.UPLOAD_ALREADY_COMPLETED,
                "上传已完成",
            )
        if status == STATUS_CANCELED:
            raise BusinessError(
                ErrorCode.UPLOAD_CANCELED,
                "上传已取消",
            )
        if status == STATUS_EXPIRED:
            raise BusinessError(
                ErrorCode.UPLOAD_EXPIRED,
                f"上传会话已过期：{session.upload_id}",
            )
        if status not in UPLOADABLE_STATUSES:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"会话处于未知状态：{status}",
            )

    def _verify_chunk_number(
        self,
        session: UploadSession,
        chunk_number: int,
    ) -> None:
        """校验分片编号位于 ``[0, totalChunks)``。

        Args:
            session: 会话对象。
            chunk_number: 分片编号。

        Raises:
            BusinessError: 编号越界。
        """
        if chunk_number < 0 or chunk_number >= session.total_chunks:
            upper = session.total_chunks - 1
            raise BusinessError(
                ErrorCode.CHUNK_OUT_OF_RANGE,
                (
                    f"分片编号越界：{chunk_number}，"
                    f"允许范围 [0, {upper}]"
                ),
            )

    def _compute_expected_chunk_size(
        self,
        session: UploadSession,
        chunk_number: int,
    ) -> int:
        """计算指定分片的期望字节数。

        非最后一片等于 ``chunkSize``；最后一片为剩余大小。

        Args:
            session: 会话对象。
            chunk_number: 分片编号。

        Returns:
            期望字节数。
        """
        if chunk_number < session.total_chunks - 1:
            return session.chunk_size
        return session.size - session.chunk_size * (
            session.total_chunks - 1
        )

    def _buffer_and_hash(
        self,
        content: BinaryIO,
        buffer: BinaryIO,
    ) -> tuple[int, str, str]:
        """将内容读入缓冲区并同时计算 MD5 与 SHA-256。

        Args:
            content: 输入流。
            buffer: 输出缓冲区。

        Returns:
            三元组 ``(总字节数, MD5 十六进制, SHA-256 十六进制)``。
        """
        md5_hasher = hashlib.md5()
        sha256_hasher = hashlib.sha256()
        total = 0
        while True:
            piece = content.read(CHUNK_READ_BUFFER_SIZE)
            if not piece:
                break
            md5_hasher.update(piece)
            sha256_hasher.update(piece)
            buffer.write(piece)
            total += len(piece)
        buffer.flush()
        return total, md5_hasher.hexdigest(), sha256_hasher.hexdigest()

    def _verify_chunk_checksum(
        self,
        expected_md5: Optional[str],
        expected_sha256: Optional[str],
        actual_md5: str,
        actual_sha256: str,
    ) -> None:
        """校验客户端提供的分片校验值。

        Args:
            expected_md5: 客户端提供的 MD5 十六进制值，可为 ``None``。
            expected_sha256: 客户端提供的 SHA-256 十六进制值，可为 ``None``。
            actual_md5: 实际计算得到的 MD5 十六进制值。
            actual_sha256: 实际计算得到的 SHA-256 十六进制值。

        Raises:
            BusinessError: 任一校验值与实际不符。
        """
        if expected_md5 is not None:
            if expected_md5.strip().lower() != actual_md5:
                raise BusinessError(
                    ErrorCode.CHECKSUM_MISMATCH,
                    "分片 Content-MD5 校验失败",
                )
        if expected_sha256 is not None:
            if expected_sha256.strip().lower() != actual_sha256:
                raise BusinessError(
                    ErrorCode.CHECKSUM_MISMATCH,
                    "分片 X-Chunk-SHA256 校验失败",
                )

    def _build_chunk_response(
        self,
        snapshot: UploadSessionSnapshot,
        chunk_number: int,
        received_size: int,
    ) -> UploadChunkResponse:
        """将快照与本次分片结果转换为响应。

        Args:
            snapshot: 会话快照。
            chunk_number: 本次接收的分片编号。
            received_size: 本次接收的字节数。

        Returns:
            分片上传响应。
        """
        return UploadChunkResponse(
            upload_id=snapshot.session.upload_id,
            chunk_number=chunk_number,
            received_size=received_size,
            uploaded_chunks=len(snapshot.uploaded_chunks),
            total_chunks=snapshot.session.total_chunks,
            uploaded_bytes=snapshot.uploaded_bytes,
            status=snapshot.session.status,  # type: ignore[arg-type]
        )


    def complete_upload(
        self,
        upload_id: str,
        request: CompleteUploadRequest,
    ) -> FileSystemEntryMetadata:
        """完成分片上传并生成目标文件。

        流程：加会话写锁 → 状态机校验 → 原子转移至 ``completing``
        → 缺失分片检查 → 路径/父目录/冲突二次校验 → 磁盘空间检查
        → 合并到临时文件 → 整体校验 → 原子提交 → 标记 ``completed``
        → 清理临时分片。任何失败都会回退状态到 ``uploading`` 并清理
        临时文件，目标文件保持不变。

        Args:
            upload_id: 上传会话 ID。
            request: 完成请求。

        Returns:
            最终文件的元数据。

        Raises:
            BusinessError: 会话不存在、已过期、状态不允许、分片缺失、
                路径越界、目标冲突、磁盘空间不足或校验失败。
        """
        with self._lock_manager.session_write_lock(upload_id):
            session = self._load_session_or_raise(upload_id)
            session = self._apply_expiry_if_needed(session)
            try:
                self._handle_completed_or_terminal(session)
            except _CompletedSignal as signal:
                return self._metadata_service.build_metadata(
                    signal.target_real, follow_link=True
                )
            session = self._transition_to_completing(session)
            snapshot = self._load_snapshot_or_raise(upload_id)
            self._verify_all_chunks_present(snapshot, upload_id)
            target_real = self._revalidate_target(session)
            self._verify_disk_space(session.size)
            expected_checksum = self._resolve_expected_checksum(
                session, request
            )
            self._merge_with_checksum(
                upload_id, session, target_real, expected_checksum
            )
            self._finalize_completion(session, target_real)
            return self._metadata_service.build_metadata(
                target_real, follow_link=True
            )

    def _handle_completed_or_terminal(
        self,
        session: UploadSession,
    ) -> None:
        """处理已完成或已终止的会话。

        Args:
            session: 会话对象。

        Raises:
            BusinessError: 会话状态不允许继续完成操作。
        """
        status = session.status
        if status == STATUS_COMPLETED:
            target_real = self._resolve_completed_target(session)
            if not target_real.exists() or not target_real.is_file():
                raise BusinessError(
                    ErrorCode.NOT_FOUND,
                    f"目标文件已不存在：{session.target_path}",
                )
            # 已完成：返回现有元数据由调用方处理（不会到达此处，因为
            # 上层仍需返回元数据）。为避免与返回值耦合，这里让
            # complete_upload 显式处理。
            raise _CompletedSignal(target_real)
        if status == STATUS_COMPLETING:
            raise BusinessError(
                ErrorCode.UPLOAD_COMPLETING,
                "上传正在合并，请稍后重试",
            )
        if status == STATUS_CANCELED:
            raise BusinessError(
                ErrorCode.UPLOAD_CANCELED,
                "上传已取消",
            )
        if status == STATUS_EXPIRED:
            raise BusinessError(
                ErrorCode.UPLOAD_EXPIRED,
                f"上传会话已过期：{session.upload_id}",
            )
        if status == STATUS_FAILED:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                "上传会话已失败，无法继续",
            )

    def _resolve_completed_target(self, session: UploadSession) -> Path:
        """解析已完成会话的目标文件真实路径。

        Args:
            session: 会话对象。

        Returns:
            目标文件真实路径。
        """
        return self._path_service.resolve_real_path(
            session.target_path, follow_link=False
        )

    def _transition_to_completing(
        self,
        session: UploadSession,
    ) -> UploadSession:
        """将会话原子转移至 ``completing``。

        Args:
            session: 会话对象。

        Returns:
            转移后的会话对象。

        Raises:
            BusinessError: 并发转移失败或状态不允许。
        """
        transitioned = self._repository.transition_status(
            session.upload_id,
            UPLOADABLE_STATUSES,
            STATUS_COMPLETING,
            time.time(),
        )
        if not transitioned:
            reloaded = self._load_session_or_raise(session.upload_id)
            self._handle_completed_or_terminal(reloaded)
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                "无法将会话转移到合并状态",
            )
        reloaded = self._repository.get_session(session.upload_id)
        if reloaded is None:
            raise BusinessError(
                ErrorCode.UPLOAD_NOT_FOUND,
                f"上传会话不存在：{session.upload_id}",
            )
        return reloaded

    def _load_snapshot_or_raise(
        self,
        upload_id: str,
    ) -> UploadSessionSnapshot:
        """读取会话快照，不存在时抛出 ``UPLOAD_NOT_FOUND``。

        Args:
            upload_id: 上传会话 ID。

        Returns:
            会话快照。

        Raises:
            BusinessError: 会话不存在。
        """
        snapshot = self._repository.get_snapshot(upload_id)
        if snapshot is None:
            raise BusinessError(
                ErrorCode.UPLOAD_NOT_FOUND,
                f"上传会话不存在：{upload_id}",
            )
        return snapshot

    def _verify_all_chunks_present(
        self,
        snapshot: UploadSessionSnapshot,
        upload_id: str,
    ) -> None:
        """校验所有分片已上传。

        Args:
            snapshot: 会话快照。
            upload_id: 上传会话 ID。

        Raises:
            BusinessError: 存在缺失分片。
        """
        if not snapshot.missing_chunks:
            return
        self._repository.transition_status(
            upload_id,
            (STATUS_COMPLETING,),
            STATUS_UPLOADING,
            time.time(),
        )
        raise BusinessError(
            ErrorCode.UPLOAD_INCOMPLETE,
            "分片未全部上传",
            details={"missingChunks": snapshot.missing_chunks},
        )

    def _revalidate_target(self, session: UploadSession) -> Path:
        """完成前重新校验目标路径。

        分片期间沙箱可能被外部修改，需要在合并前再次校验路径仍在
        沙箱内、父目录存在、目标不冲突。

        Args:
            session: 会话对象。

        Returns:
            目标文件真实路径。

        Raises:
            BusinessError: 路径越界、父目录缺失或目标冲突。
        """
        target_real = self._path_service.resolve_real_path(
            session.target_path, follow_link=False
        )
        self._path_service.ensure_parent_exists(target_real)
        if target_real.is_dir():
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标已存在且为目录：{target_real.name}",
            )
        exists = target_real.exists() or target_real.is_symlink()
        if exists and not session.overwrite:
            raise BusinessError(
                ErrorCode.FILE_EXISTS,
                f"目标文件已存在：{target_real.name}",
            )
        return target_real

    def _resolve_expected_checksum(
        self,
        session: UploadSession,
        request: CompleteUploadRequest,
    ) -> Optional[ChecksumSchema]:
        """确定本次完成要使用的整体校验信息。

        优先使用完成请求中提供的 checksum；否则回退到初始化时
        记录的值。

        Args:
            session: 会话对象。
            request: 完成请求。

        Returns:
            校验信息；未提供时返回 ``None``。
        """
        if request.checksum is not None:
            return request.checksum
        if session.checksum_algorithm and session.checksum_value:
            return ChecksumSchema(
                algorithm=session.checksum_algorithm,  # type: ignore[arg-type]
                value=session.checksum_value,
            )
        return None

    def _merge_with_checksum(
        self,
        upload_id: str,
        session: UploadSession,
        target_real: Path,
        expected_checksum: Optional[ChecksumSchema],
    ) -> None:
        """合并分片并可选地校验整体 checksum。

        Args:
            upload_id: 上传会话 ID。
            session: 会话对象。
            target_real: 目标文件真实路径。
            expected_checksum: 整体校验信息，可为 ``None``。

        Raises:
            BusinessError: 合并失败或校验失败。
        """
        try:
            with self._storage.staged_merge(
                upload_id, session.total_chunks, target_real
            ) as temp_path:
                if expected_checksum is not None:
                    self._verify_file_checksum(
                        temp_path, expected_checksum
                    )
        except BusinessError:
            self._revert_to_uploading(upload_id)
            raise
        except OSError as exc:
            self._revert_to_uploading(upload_id)
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"合并分片失败：{upload_id}",
            ) from exc

    def _verify_file_checksum(
        self,
        file_path: Path,
        checksum: ChecksumSchema,
    ) -> None:
        """校验合并后文件的整体 checksum。

        Args:
            file_path: 待校验文件路径。
            checksum: 校验信息。

        Raises:
            BusinessError: 校验失败。
        """
        if checksum.algorithm == "sha256":
            hasher = hashlib.sha256()
        elif checksum.algorithm == "md5":
            hasher = hashlib.md5()
        else:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                f"不支持的校验算法：{checksum.algorithm}",
            )

        with file_path.open("rb") as file_handle:
            while True:
                block = file_handle.read(CHUNK_READ_BUFFER_SIZE)
                if not block:
                    break
                hasher.update(block)

        actual = hasher.hexdigest()
        expected = checksum.value.strip().lower()
        if actual != expected:
            raise BusinessError(
                ErrorCode.CHECKSUM_MISMATCH,
                "整体校验失败",
                details={
                    "algorithm": checksum.algorithm,
                    "expected": expected,
                    "actual": actual,
                },
            )

    def _revert_to_uploading(self, upload_id: str) -> None:
        """完成失败时回退状态到 ``uploading``，便于客户端重试。

        Args:
            upload_id: 上传会话 ID。
        """
        self._repository.transition_status(
            upload_id,
            (STATUS_COMPLETING,),
            STATUS_UPLOADING,
            time.time(),
        )

    def _finalize_completion(
        self,
        session: UploadSession,
        target_real: Path,
    ) -> None:
        """完成后标记状态并清理临时分片。

        Args:
            session: 会话对象。
            target_real: 目标文件真实路径。
        """
        del target_real  # 目前仅用于语义说明，未在逻辑中读取。
        self._repository.transition_status(
            session.upload_id,
            (STATUS_COMPLETING,),
            STATUS_COMPLETED,
            time.time(),
        )
        self._storage.cleanup_session(session.upload_id)


    def cancel_upload(self, upload_id: str) -> None:
        """取消上传会话并清理临时数据。

        幂等：会话不存在时静默返回。已过期会话在清理临时数据后
        删除元数据；已取消会话重复调用同样返回。已完成会话返回
        ``UPLOAD_ALREADY_COMPLETED``，正在合并的会话返回
        ``UPLOAD_COMPLETING``。

        Args:
            upload_id: 上传会话 ID。

        Raises:
            BusinessError: 会话正在合并或已完成。
        """
        with self._lock_manager.session_write_lock(upload_id):
            session = self._repository.get_session(upload_id)
            if session is None:
                return
            session = self._apply_expiry_if_needed(session)
            status = session.status
            if status == STATUS_COMPLETED:
                raise BusinessError(
                    ErrorCode.UPLOAD_ALREADY_COMPLETED,
                    "上传已完成，无法取消",
                )
            if status == STATUS_COMPLETING:
                raise BusinessError(
                    ErrorCode.UPLOAD_COMPLETING,
                    "上传正在合并，无法取消",
                )
            self._repository.transition_status(
                upload_id,
                (
                    STATUS_CREATED,
                    STATUS_UPLOADING,
                    STATUS_CANCELED,
                    STATUS_EXPIRED,
                ),
                STATUS_CANCELED,
                time.time(),
            )
            self._storage.cleanup_session(upload_id)
            self._repository.delete_session(upload_id)


class _CompletedSignal(Exception):
    """内部信号：会话已完成，需要返回现有文件元数据。

    该异常不会离开 :class:`ChunkedUploadService`，仅用于在
    :meth:`_handle_completed_or_terminal` 中早退，让上层分支代码
    保持整洁。
    """

    def __init__(self, target_real: Path) -> None:
        """构造信号。

        Args:
            target_real: 目标文件的真实路径。
        """
        super().__init__("completed")
        self.target_real: Path = target_real


__all__ = [
    "ChunkedUploadService",
    "EXPIRY_ELIGIBLE_STATUSES",
    "UPLOADABLE_STATUSES",
]
