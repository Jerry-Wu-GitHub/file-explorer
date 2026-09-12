"""统一响应外壳与基础 Schema 定义。

本模块定义所有业务 Schema 的公共基类 :class:`BaseSchema`，
以及统一的成功响应外壳 :class:`ApiResponse`、错误响应
:class:`ErrorResponse` 与分页元数据 :class:`PageMeta`。

所有业务 Schema 必须继承 :class:`BaseSchema`，以自动获得小驼峰
别名、双命名兼容、禁止额外字段等全局规则。
"""

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    """所有业务 Schema 的公共基类。

    统一配置：

    - 自动生成小驼峰别名（``created_at`` -> ``createdAt``）；
    - 允许使用字段原名或别名两种命名传入；
    - 禁止传入未定义的字段，避免请求体中混入垃圾数据。
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class ErrorResponse(BaseSchema):
    """统一错误响应模型。

    所有失败响应，无论来自业务异常、参数校验还是未捕获异常，
    都必须使用该模型进行序列化，保证前端只需处理一种错误结构。
    """

    code: str = Field(
        description="业务错误码，语义化大写字符串，例如 INVALID_PATH",
    )

    message: str = Field(
        description="人类可读的错误提示文案",
    )

    details: Optional[dict[str, Any]] = Field(
        description="附加详情，存放扩展上下文，例如 missingChunks",
        default=None,
    )

    request_id: Optional[str] = Field(
        description="请求追踪 ID，便于日志关联",
        default=None,
    )


Data = TypeVar("Data")
"""泛型类型变量，代表任意业务数据类型。"""


class PageMeta(BaseSchema):
    """分页元数据。

    用于目录列表、搜索结果等分页接口，通常附加在
    :class:`ApiResponse.meta` 字段中。
    """

    total: int = Field(
        description="满足条件的条目总数",
    )

    page: int = Field(
        description="当前页码，从 1 开始",
    )

    size: int = Field(
        description="每页条目数量",
    )


class ApiResponse(BaseSchema, Generic[Data]):
    """统一成功响应外壳模型。

    所有成功响应都使用该模型进行序列化，``data`` 字段承载业务数据，
    ``meta`` 字段承载分页等附加信息。
    """

    data: Optional[Data] = Field(
        description="业务数据",
        default=None,
    )

    meta: Optional[dict[str, Any]] = Field(
        description="元数据，例如分页信息",
        default=None,
    )


__all__ = [
    "BaseSchema",
    "ErrorResponse",
    "PageMeta",
    "ApiResponse",
    "Data",
]
