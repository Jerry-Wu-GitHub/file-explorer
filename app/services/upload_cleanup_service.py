"""分片上传的后台清理任务。

本模块提供 :class:`UploadCleanupService`，定期扫描数据库中已过期
但仍处于活动状态的上传会话，将会话标记为 ``expired`` 并清理其
临时分片目录。会话元数据保留为墓碑，使后续请求仍能返回
``410 UPLOAD_EXPIRED``，而不是被误判为不存在的会话。
"""

import asyncio
import logging
import time
from typing import Optional

from ..constants import (
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_UPLOADING,
)
from ..repositories.upload_session_repository import (
    UploadSessionRepository,
)
from ..storage.upload_chunk_storage import LocalUploadChunkStorage


logger = logging.getLogger(__name__)


CLEANUP_SHUTDOWN_TIMEOUT_SECONDS: float = 5.0
"""关闭清理任务时的等待超时（秒）。"""

MIN_CLEANUP_INTERVAL_SECONDS: float = 0.01
"""清理间隔的下界，用于避免配置错误导致忙循环。"""

EXPIRABLE_STATUSES: tuple[str, ...] = (STATUS_CREATED, STATUS_UPLOADING)
"""允许被标记为过期的会话状态集合。"""


class UploadCleanupService:
    """过期上传会话的后台清理服务。

    Attributes:
        repository: 上传会话仓储。
        storage: 分片文件存储。
        interval_seconds: 两次清理之间的间隔（秒）。
    """

    def __init__(
        self,
        repository: UploadSessionRepository,
        storage: LocalUploadChunkStorage,
        interval_seconds: float,
    ) -> None:
        """构造清理服务。

        Args:
            repository: 上传会话仓储。
            storage: 分片文件存储。
            interval_seconds: 两次清理之间的间隔（秒），会被限制为
                不低于 :data:`MIN_CLEANUP_INTERVAL_SECONDS`。
        """
        self._repository: UploadSessionRepository = repository
        self._storage: LocalUploadChunkStorage = storage
        self._interval_seconds: float = max(
            MIN_CLEANUP_INTERVAL_SECONDS, float(interval_seconds)
        )

    @property
    def interval_seconds(self) -> float:
        """返回两次清理之间的实际间隔（秒）。

        Returns:
            间隔秒数。
        """
        return self._interval_seconds

    def cleanup_once(self, now: Optional[float] = None) -> int:
        """执行一次清理。

        仅处理状态为 ``created`` 或 ``uploading`` 且已过期的会话；
        对每个会话使用原子状态转移避免与请求处理路径竞争。

        Args:
            now: 当前时间戳；未提供时使用 :func:`time.time`。

        Returns:
            本次实际标记为过期并清理的会话数量。
        """
        timestamp = time.time() if now is None else now
        expired_sessions = self._repository.list_expired_sessions(timestamp)
        cleaned_count = 0
        for session in expired_sessions:
            transitioned = self._repository.transition_status(
                session.upload_id,
                EXPIRABLE_STATUSES,
                STATUS_EXPIRED,
                timestamp,
            )
            if not transitioned:
                continue
            self._storage.cleanup_session(session.upload_id)
            cleaned_count += 1
        if cleaned_count > 0:
            logger.info("已清理 %d 个过期上传会话", cleaned_count)
        return cleaned_count

    async def run_periodically(self, stop_event: asyncio.Event) -> None:
        """周期性执行清理，直到 ``stop_event`` 被设置。

        每次迭代内部的异常都会被捕获并记录，避免单次失败终止整个
        循环；等待间隔期间取消会正常退出。

        Args:
            stop_event: 用于请求停止循环的事件对象。
        """
        logger.info(
            "上传清理任务启动，间隔 %.2f 秒", self._interval_seconds
        )
        while not stop_event.is_set():
            try:
                self.cleanup_once()
            except Exception:
                logger.exception("上传清理任务执行失败")
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self._interval_seconds,
                )
            except asyncio.TimeoutError:
                pass
        logger.info("上传清理任务已停止")


__all__ = [
    "UploadCleanupService",
    "CLEANUP_SHUTDOWN_TIMEOUT_SECONDS",
    "MIN_CLEANUP_INTERVAL_SECONDS",
    "EXPIRABLE_STATUSES",
]
