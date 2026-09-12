"""分片上传的请求与响应 Schema。

本模块定义分片上传接口所需的 Pydantic 模型，包括初始化请求、
校验信息、以及统一的会话状态响应。所有字段继承
:class:`app.schemas.base.BaseSchema`，自动获得小驼峰别名、双命名
兼容、禁止额外字段等全局规则。
"""

from typing import Literal, Optional

from pydantic import Field

from ..constants import (
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
)
from .base import BaseSchema


UploadStatus = Literal[
    "created",
    "uploading",
    "completing",
    "completed",
    "canceled",
    "expired",
    "failed",
]
"""上传会话状态字面量，与 :mod:`app.constants.upload` 保持一致。"""

ChecksumAlgorithm = Literal["sha256", "md5"]
"""支持的校验算法字面量，与 :mod:`app.constants.upload` 保持一致。"""


class ChecksumSchema(BaseSchema):
    """整体或分片校验信息。"""

    algorithm: ChecksumAlgorithm = Field(
        description="校验算法，至少支持 sha256，也支持 md5",
    )

    value: str = Field(
        description="十六进制校验值，大小写不敏感",
        min_length=1,
    )


class InitializeUploadRequest(BaseSchema):
    """初始化分片上传的请求体。"""

    path: str = Field(
        description=(
            "目标文件的沙箱虚拟绝对路径，必须包含文件名，"
            "不能以 / 结尾"
        ),
        min_length=1,
    )

    size: int = Field(
        description="文件总字节数，必须大于等于 0",
        ge=0,
    )

    chunk_size: Optional[int] = Field(
        description=(
            "分片大小（字节），必须在最小与最大分片大小之间；"
            "未提供时使用服务端默认值"
        ),
        default=None,
        ge=MIN_CHUNK_SIZE,
        le=MAX_CHUNK_SIZE,
    )

    overwrite: bool = Field(
        description="目标文件已存在时是否允许覆盖",
        default=False,
    )

    checksum: Optional[ChecksumSchema] = Field(
        description="整体校验信息，用于完成时校验合并后的文件",
        default=None,
    )


class UploadSessionResponse(BaseSchema):
    """上传会话状态响应。

    同时用于初始化响应与状态查询响应。``uploadedChunks`` 与
    ``missingChunks`` 为当前已上传/未上传的分片编号列表，按升序
    排列；``uploadedBytes`` 为已上传字节数之和。
    """

    upload_id: str = Field(
        description="上传会话 ID，由服务端生成的高熵随机值",
    )

    path: str = Field(
        description="目标文件的沙箱虚拟绝对路径",
    )

    size: int = Field(
        description="文件总字节数",
        ge=0,
    )

    chunk_size: int = Field(
        description="分片大小（字节）",
        ge=1,
    )

    total_chunks: int = Field(
        description="分片总数，等于 ceil(size / chunkSize)",
        ge=0,
    )

    uploaded_chunks: list[int] = Field(
        description="已上传分片编号列表，升序",
    )

    missing_chunks: list[int] = Field(
        description="缺失分片编号列表，升序",
    )

    uploaded_bytes: int = Field(
        description="已上传的总字节数",
        ge=0,
    )

    status: UploadStatus = Field(
        description="会话状态",
    )

    created_at: float = Field(
        description="创建时间（Unix 时间戳，单位：秒）",
    )

    updated_at: float = Field(
        description="最后更新时间（Unix 时间戳，单位：秒）",
    )

    expires_at: float = Field(
        description="过期时间（Unix 时间戳，单位：秒）",
    )


class UploadChunkResponse(BaseSchema):
    """分片上传响应。

    与 :class:`UploadSessionResponse` 不同，本响应的
    ``uploadedChunks`` 表示已上传分片的**数量**，用于描述单次分片
    上传操作的结果。
    """

    upload_id: str = Field(
        description="上传会话 ID",
    )

    chunk_number: int = Field(
        description="本次接收的分片编号，从 0 开始",
        ge=0,
    )

    received_size: int = Field(
        description="本次分片实际接收的字节数",
        ge=0,
    )

    uploaded_chunks: int = Field(
        description="会话当前已上传分片的总数",
        ge=0,
    )

    total_chunks: int = Field(
        description="会话的分片总数",
        ge=0,
    )

    uploaded_bytes: int = Field(
        description="会话当前已上传的总字节数",
        ge=0,
    )

    status: UploadStatus = Field(
        description="会话当前状态",
    )


class CompleteUploadRequest(BaseSchema):
    """完成分片上传的请求体。

    ``checksum`` 为可选。若提供，会覆盖初始化时的配置；若未提供，
    则使用初始化时记录的整体校验信息（如有）。两者都没有时不
    校验整体 checksum。
    """

    checksum: Optional[ChecksumSchema] = Field(
        description="整体校验信息，用于校验合并后的文件",
        default=None,
    )


__all__ = [
    "UploadStatus",
    "ChecksumAlgorithm",
    "ChecksumSchema",
    "InitializeUploadRequest",
    "UploadSessionResponse",
    "UploadChunkResponse",
    "CompleteUploadRequest",
]
