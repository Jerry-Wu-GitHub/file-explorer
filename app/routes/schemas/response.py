"""API 响应体 Schema。"""

from typing import Optional

from pydantic import Field

from app.models.common import BaseSchema
from app.models.fs_entry import FsEntry
from app.models.upload_session import UploadSession


class UploadSessionResponse(BaseSchema):
    """分片上传会话状态响应"""

    upload_id: str = Field(
        description="上传会话 ID",
    )

    path: str = Field(
        description="目标文件沙箱虚拟绝对路径",
    )

    size: int = Field(
        description="文件总字节数",
    )

    chunk_size: int = Field(
        description="分片大小（字节）",
    )

    total_chunks: int = Field(
        description="总分片数量",
    )

    uploaded_chunks: list[int] = Field(
        description="已上传分片编号列表",
    )

    missing_chunks: list[int] = Field(
        description="缺失分片编号列表",
    )

    uploaded_bytes: int = Field(
        description="已上传字节数",
    )

    status: str = Field(
        description="上传状态",
    )

    created_at: float = Field(
        description="创建时间（Unix 时间戳，秒）",
    )

    updated_at: float = Field(
        description="最近更新时间（Unix 时间戳，秒）",
    )

    expires_at: float = Field(
        description="过期时间（Unix 时间戳，秒）",
    )

    final_entry: Optional[FsEntry] = Field(
        description="已完成会话的最终文件元数据",
        default=None,
    )


class ChunkUploadResponse(BaseSchema):
    """分片上传结果响应"""

    upload_id: str = Field(
        description="上传会话 ID",
    )

    chunk_number: int = Field(
        description="本次上传的分片编号",
    )

    received_size: int = Field(
        description="本次接收的字节数",
    )

    uploaded_chunks: int = Field(
        description="已上传分片数量",
    )

    total_chunks: int = Field(
        description="总分片数量",
    )

    uploaded_bytes: int = Field(
        description="已上传字节数",
    )

    status: str = Field(
        description="当前上传状态",
    )


def build_upload_session_response(
    session: UploadSession,
    final_entry: Optional[FsEntry] = None,
) -> UploadSessionResponse:
    """将内部会话模型转换为会话状态响应。"""
    total_chunks: int = session.total_chunks
    uploaded_set: set[int] = set(session.uploaded_chunks)
    missing_chunks: list[int] = [
        number for number in range(total_chunks) if number not in uploaded_set
    ]
    return UploadSessionResponse(
        upload_id=session.upload_id,
        path=session.path,
        size=session.size,
        chunk_size=session.chunk_size,
        total_chunks=session.total_chunks,
        uploaded_chunks=sorted(session.uploaded_chunks),
        missing_chunks=missing_chunks,
        uploaded_bytes=session.uploaded_bytes,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        expires_at=session.expires_at,
        final_entry=final_entry,
    )
