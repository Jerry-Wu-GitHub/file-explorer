"""分片上传会话的数据模型。

本模块定义上传会话、分片记录与会话快照三个内部数据模型，用于在
服务层与持久化层之间传递数据，不直接参与 HTTP 序列化。对外的
请求与响应模型定义在 :mod:`app.schemas.upload`。
"""

from dataclasses import dataclass, field
from typing import Optional

from app.constants import (
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_COMPLETING,
    STATUS_CREATED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_UPLOADING,
)


UPLOAD_STATUSES: tuple[str, ...] = (
    STATUS_CREATED,
    STATUS_UPLOADING,
    STATUS_COMPLETING,
    STATUS_COMPLETED,
    STATUS_CANCELED,
    STATUS_EXPIRED,
    STATUS_FAILED,
)
"""所有合法的会话状态。"""

ACTIVE_STATUSES: tuple[str, ...] = (
    STATUS_CREATED,
    STATUS_UPLOADING,
    STATUS_COMPLETING,
)
"""视为「活动」的会话状态，用于并发会话数统计与清理筛选。"""

TERMINAL_STATUSES: tuple[str, ...] = (
    STATUS_COMPLETED,
    STATUS_CANCELED,
    STATUS_EXPIRED,
    STATUS_FAILED,
)
"""终止状态，不可再转移。"""


@dataclass(frozen=True)
class UploadSession:
    """分片上传会话。

    描述一次分片上传从初始化到完成（或取消、过期）的完整状态。
    所有时间字段均为 Unix 时间戳（单位：秒）。
    """

    upload_id: str = field(
        metadata={"description": "上传会话 ID，使用 UUIDv4"}
    )

    target_path: str = field(
        metadata={"description": "目标文件的沙箱虚拟绝对路径"}
    )

    size: int = field(
        metadata={"description": "文件总字节数"}
    )

    chunk_size: int = field(
        metadata={"description": "分片大小（字节）"}
    )

    total_chunks: int = field(
        metadata={"description": "分片总数"}
    )

    overwrite: bool = field(
        metadata={"description": "目标已存在时是否允许覆盖"}
    )

    checksum_algorithm: Optional[str] = field(
        metadata={"description": "整体校验算法，例如 sha256；未提供时为 None"}
    )

    checksum_value: Optional[str] = field(
        metadata={"description": "整体校验值十六进制字符串；未提供时为 None"}
    )

    status: str = field(
        metadata={"description": "会话状态，取值见 UPLOAD_STATUSES"}
    )

    created_at: float = field(
        metadata={"description": "创建时间（Unix 时间戳，单位：秒）"}
    )

    updated_at: float = field(
        metadata={"description": "最后更新时间（Unix 时间戳，单位：秒）"}
    )

    expires_at: float = field(
        metadata={"description": "过期时间（Unix 时间戳，单位：秒）"}
    )


@dataclass(frozen=True)
class UploadChunkRecord:
    """已上传分片的记录。

    分片文件本身存放在临时目录中，本记录只保存编号与大小，用于
    断点续传与合并时校验。
    """

    upload_id: str = field(
        metadata={"description": "所属上传会话 ID"}
    )

    chunk_number: int = field(
        metadata={"description": "分片编号，从 0 开始"}
    )

    received_size: int = field(
        metadata={"description": "分片实际接收的字节数"}
    )

    updated_at: float = field(
        metadata={"description": "分片最后写入时间（Unix 时间戳，单位：秒）"}
    )


@dataclass(frozen=True)
class UploadSessionSnapshot:
    """会话快照，包含已上传分片信息。

    面向服务层，用于生成对外状态响应；封装了从会话基础信息与
    分片记录集合计算派生字段的逻辑，避免服务层直接拼装。
    """

    session: UploadSession = field(
        metadata={"description": "会话基础信息"}
    )

    uploaded_chunks: list[int] = field(
        metadata={"description": "已上传分片编号列表，升序"}
    )

    uploaded_bytes: int = field(
        metadata={"description": "已上传的总字节数"}
    )

    @property
    def missing_chunks(self) -> list[int]:
        """返回尚未上传的分片编号列表，升序。

        Returns:
            缺失分片编号列表。
        """
        uploaded_set = set(self.uploaded_chunks)
        return [
            chunk_number
            for chunk_number in range(self.session.total_chunks)
            if chunk_number not in uploaded_set
        ]


__all__ = [
    "UPLOAD_STATUSES",
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "UploadSession",
    "UploadChunkRecord",
    "UploadSessionSnapshot",
]
