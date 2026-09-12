"""业务领域模型包。

本包集中定义不直接参与 HTTP 序列化的内部数据模型。
"""

from app.models.upload_session import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    UPLOAD_STATUSES,
    UploadChunkRecord,
    UploadSession,
    UploadSessionSnapshot,
)

__all__ = [
    "UploadSession",
    "UploadChunkRecord",
    "UploadSessionSnapshot",
    "UPLOAD_STATUSES",
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
]
