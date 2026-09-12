"""API 请求体 Schema。"""

from typing import Optional

from pydantic import Field, model_validator

from app.models.common import BaseSchema


class ChecksumSchema(BaseSchema):
    """整体校验信息"""

    algorithm: str = Field(
        description="校验算法，如 sha256",
    )

    value: str = Field(
        description="十六进制校验值",
    )


class CreateFileRequest(BaseSchema):
    """创建文件（或符号链接）请求体"""

    path: str = Field(
        description="沙箱虚拟绝对路径",
    )

    link_target: Optional[str] = Field(
        description="创建符号链接时的链接目标（提供时创建符号链接）",
        default=None,
    )


class CreateFolderRequest(BaseSchema):
    """创建文件夹请求体"""

    path: str = Field(
        description="沙箱虚拟绝对路径",
    )


class PatchMetadataRequest(BaseSchema):
    """修改元数据请求体，传什么字段就修改什么"""

    name: Optional[str] = Field(
        description="新名称（与 path 同时给出时无效）",
        default=None,
    )

    path: Optional[str] = Field(
        description="新绝对路径（相当于移动+重命名）",
        default=None,
    )

    modified_at: Optional[float] = Field(
        description="修改时间（Unix 时间戳，秒）",
        default=None,
        ge=0,
    )

    accessed_at: Optional[float] = Field(
        description="访问时间（Unix 时间戳，秒）",
        default=None,
        ge=0,
    )

    permissions: Optional[str] = Field(
        description="权限字符串，如 rw-r--r--",
        default=None,
        min_length=9,
        max_length=9,
    )

    is_hidden: Optional[bool] = Field(
        description="是否是隐藏项目",
        default=None,
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "PatchMetadataRequest":
        """至少提供一个待修改字段。"""
        fields: tuple[Optional[object], ...] = (
            self.name,
            self.path,
            self.modified_at,
            self.accessed_at,
            self.permissions,
            self.is_hidden,
        )
        if all(field is None for field in fields):
            raise ValueError("至少提供一个待修改字段")
        return self


class InitUploadRequest(BaseSchema):
    """初始化分片上传请求体"""

    path: str = Field(
        description="目标文件沙箱内路径，必须包含文件名，不能以 / 结尾",
    )

    size: int = Field(
        description="文件总字节数",
        ge=0,
    )

    chunk_size: Optional[int] = Field(
        description="分片大小（字节），默认取服务端配置",
        default=None,
        ge=1,
    )

    overwrite: bool = Field(
        description="目标文件已存在时是否允许覆盖",
        default=False,
    )

    checksum: Optional[ChecksumSchema] = Field(
        description="整体校验信息，用于完成时校验合并后的文件",
        default=None,
    )


class CompleteUploadRequest(BaseSchema):
    """完成分片上传请求体"""

    checksum: Optional[ChecksumSchema] = Field(
        description="整体校验信息，以本次传入为准",
        default=None,
    )


class CopyRequest(BaseSchema):
    """复制请求体"""

    source: str = Field(
        description="源路径（沙箱虚拟绝对路径）",
    )

    destination: str = Field(
        description="目标路径（沙箱虚拟绝对路径）",
    )

    overwrite: bool = Field(
        description="目标已存在时是否允许覆盖",
        default=False,
    )
