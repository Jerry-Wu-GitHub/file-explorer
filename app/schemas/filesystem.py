"""文件系统相关的请求与响应 Schema。

本模块定义文件资源管理器业务中最核心的数据模型：

- :class:`FileSystemEntryMetadata`：文件系统条目元数据；
- :class:`ListDirectoryQuery`：目录列表接口的查询参数模型。

所有字段均继承 :class:`app.schemas.base.BaseSchema`，自动获得小
驼峰别名、双命名兼容、禁止额外字段等全局规则。
"""

from typing import Literal, Optional

from pydantic import Field

from ..constants import (
    DEFAULT_FILTER_TYPE,
    DEFAULT_FOLLOW_LINK,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_FIELD,
    DEFAULT_SORT_ORDER,
    MAX_PAGE_SIZE,
    MIN_PAGE,
    MIN_PAGE_SIZE,
)
from .base import BaseSchema


FileSystemEntryType = Literal["file", "directory", "link", "other"]
"""文件系统条目类型字面量。"""

DirectoryFilterType = Literal["all", "file", "directory"]
"""目录列表过滤类型字面量。"""


class FileSystemEntryMetadata(BaseSchema):
    """文件系统条目元数据。

    描述沙箱内一个文件、目录或符号链接的基本信息。目录不计算
    大小与 MIME 类型，符号链接在不跟随模式下也不计算。
    """

    name: str = Field(
        description="条目名称，不含路径分隔符",
    )

    path: str = Field(
        description="条目在沙箱内的虚拟绝对路径，以 / 开头",
    )

    type: FileSystemEntryType = Field(
        description="条目类型：file / directory / link / other",
    )

    mime_type: Optional[str] = Field(
        description="MIME 类型；目录或无法识别时为 None",
        default=None,
    )

    size: int = Field(
        description="文件大小（字节）；目录或符号链接为 0",
        ge=0,
    )

    created_at: float = Field(
        description="创建时间（Unix 时间戳，单位：秒）",
    )

    modified_at: float = Field(
        description="修改时间（Unix 时间戳，单位：秒）",
    )

    accessed_at: float = Field(
        description="访问时间（Unix 时间戳，单位：秒）",
    )

    permissions: str = Field(
        description="权限字符串，例如 rw-r--r--",
    )

    is_hidden: bool = Field(
        description="是否为隐藏项目，名称以 . 开头视为隐藏",
    )


class ListDirectoryQuery(BaseSchema):
    """目录列表接口的查询参数模型。

    用于 ``GET /api/v1/files`` 的查询字符串，FastAPI 通过
    ``Depends`` 将其注入路由处理函数。
    """

    path: str = Field(
        description="要列出的目录虚拟路径，以 / 开头，默认为根目录",
        default="/",
    )

    page: int = Field(
        description="页码，从 1 开始",
        default=DEFAULT_PAGE,
        ge=MIN_PAGE,
    )

    size: int = Field(
        description="每页条目数量",
        default=DEFAULT_PAGE_SIZE,
        ge=MIN_PAGE_SIZE,
        le=MAX_PAGE_SIZE,
    )

    sort: str = Field(
        description=(
            "排序表达式，格式为 '<字段>,<方向>'，方向为 asc 或 desc。"
            "支持字段：name、size、modifiedAt、createdAt、accessedAt、type。"
            "默认为 'name,asc'。"
        ),
        default=f"{DEFAULT_SORT_FIELD},{DEFAULT_SORT_ORDER}",
    )

    type: DirectoryFilterType = Field(
        description="过滤类型：all / file / directory",
        default=DEFAULT_FILTER_TYPE,
    )

    follow_link: bool = Field(
        description=(
            "是否跟随符号链接；为 true 时递归解析链接指向，"
            "为 false 时把符号链接作为 link 返回"
        ),
        default=DEFAULT_FOLLOW_LINK,
    )


__all__ = [
    "FileSystemEntryMetadata",
    "ListDirectoryQuery",
    "FileSystemEntryType",
    "DirectoryFilterType",
]
