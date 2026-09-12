"""写操作的请求 Schema。

本模块定义创建、删除、修改元数据、复制四类写操作的请求模型。
所有字段继承 :class:`app.schemas.base.BaseSchema`，自动获得小驼峰
别名、双命名兼容、禁止额外字段等全局规则。
"""

from typing import Optional

from pydantic import Field

from .base import BaseSchema


class CreateFileRequest(BaseSchema):
    """创建空文件的请求体。"""

    path: str = Field(
        description="要创建的文件的沙箱虚拟绝对路径，必须包含文件名",
        min_length=1,
    )


class CreateFolderRequest(BaseSchema):
    """创建文件夹的请求体。"""

    path: str = Field(
        description="要创建的文件夹的沙箱虚拟绝对路径",
        min_length=1,
    )


class UpdateMetadataRequest(BaseSchema):
    """修改元数据的请求体。

    只有显式提供的字段才会被修改，未提供的字段保持原值。
    若同时提供 ``name`` 与 ``path``，则 ``name`` 被忽略，只按
    ``path`` 处理。
    """

    name: Optional[str] = Field(
        description="新名称（仅重命名，不改变所在目录）",
        default=None,
        min_length=1,
    )

    path: Optional[str] = Field(
        description="新绝对虚拟路径（相当于移动 + 重命名）",
        default=None,
        min_length=1,
    )

    modified_at: Optional[float] = Field(
        description="新的修改时间（Unix 时间戳，单位：秒）",
        default=None,
    )

    accessed_at: Optional[float] = Field(
        description="新的访问时间（Unix 时间戳，单位：秒）",
        default=None,
    )

    permissions: Optional[str] = Field(
        description=(
            "新的权限字符串，格式为 rwxr-xr-x。"
            "在 Windows 上仅能切换只读位，无法设置完整权限。"
        ),
        default=None,
        min_length=9,
        max_length=9,
    )

    is_hidden: Optional[bool] = Field(
        description="是否隐藏；通过增删前导点切换",
        default=None,
    )


class CopyEntryRequest(BaseSchema):
    """复制文件或文件夹的请求体。"""

    source: str = Field(
        description="源路径的沙箱虚拟绝对路径",
        min_length=1,
    )

    destination: str = Field(
        description="目标路径的沙箱虚拟绝对路径，必须包含文件名",
        min_length=1,
    )

    overwrite: bool = Field(
        description="目标已存在时是否覆盖",
        default=False,
    )


__all__ = [
    "CreateFileRequest",
    "CreateFolderRequest",
    "UpdateMetadataRequest",
    "CopyEntryRequest",
]
