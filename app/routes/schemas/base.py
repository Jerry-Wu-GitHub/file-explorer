"""兼容层：从 :mod:`app.schemas.base` 重新导出公共 Schema。

本模块保留以兼容既有引用路径，新代码请直接从
:mod:`app.schemas.base` 导入。
"""

from app.schemas.base import (
    ApiResponse,
    BaseSchema,
    Data,
    ErrorResponse,
    PageMeta,
)

__all__ = [
    "BaseSchema",
    "ErrorResponse",
    "PageMeta",
    "ApiResponse",
    "Data",
]
