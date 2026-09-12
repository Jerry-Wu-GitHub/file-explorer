"""分片上传会话模型（内部持久化模型，与 API 响应模型分离）。"""

from typing import Optional

from pydantic import Field

from app.models.common import BaseSchema


class UploadSession(BaseSchema):
    """上传会话元数据，持久化为 JSON 文件，支持多 worker 共享"""

    upload_id: str = Field(
        description="服务端生成的高熵上传会话 ID",
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
        description="总分片数量",
        ge=0,
    )

    uploaded_chunks: list[int] = Field(
        description="已上传完成的分片编号列表",
        default_factory=list,
    )

    uploaded_bytes: int = Field(
        description="已上传字节数",
        default=0,
        ge=0,
    )

    status: str = Field(
        description="上传状态：created/uploading/completing/completed/canceled/expired",
    )

    overwrite: bool = Field(
        description="目标文件已存在时是否允许覆盖",
        default=False,
    )

    checksum_algorithm: Optional[str] = Field(
        description="整体校验算法，如 sha256",
        default=None,
    )

    checksum_value: Optional[str] = Field(
        description="整体校验值（十六进制）",
        default=None,
    )

    created_at: float = Field(
        description="会话创建时间（Unix 时间戳，秒）",
    )

    updated_at: float = Field(
        description="最近更新时间（Unix 时间戳，秒）",
    )

    expires_at: float = Field(
        description="会话过期时间（Unix 时间戳，秒）",
    )
