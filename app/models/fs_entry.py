"""文件系统条目元数据模型。"""

from typing import Literal, Optional

from pydantic import Field

from app.models.common import BaseSchema


# 文件系统条目类型
FsEntryType = Literal["file", "directory", "link"]


class FsEntry(BaseSchema):
    """文件系统条目元数据，用于目录列表、属性查询等响应"""

    name: str = Field(
        description="条目名称",
    )

    path: str = Field(
        description="沙箱虚拟绝对路径，以 / 开头",
    )

    type: FsEntryType = Field(
        description="条目类型：file、directory 或 link",
    )

    mime_type: Optional[str] = Field(
        description="MIME 类型，仅文件有效，文件夹为 null",
        default=None,
    )

    size: int = Field(
        description="文件大小（字节），文件夹为 0",
        default=0,
        ge=0,
    )

    created_at: float = Field(
        description="创建时间（Unix 时间戳，秒）",
    )

    modified_at: float = Field(
        description="修改时间（Unix 时间戳，秒）",
    )

    accessed_at: float = Field(
        description="访问时间（Unix 时间戳，秒）",
    )

    permissions: str = Field(
        description="权限字符串，如 rw-r--r--",
    )

    is_hidden: bool = Field(
        description="是否是隐藏项目（名称以点开头）",
        default=False,
    )
