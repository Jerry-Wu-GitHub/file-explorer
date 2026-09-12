"""搜索接口的请求 Schema。

本模块定义 ``GET /api/v1/files/search`` 的查询参数模型。所有字段
继承 :class:`app.schemas.base.BaseSchema`，自动获得小驼峰别名、
双命名兼容、禁止额外字段等全局规则。

跨字段校验（``minSize <= maxSize``）放在
:class:`app.services.search_service.SearchService` 中执行，以避免
FastAPI 在使用 ``Depends()`` 注入 Pydantic 模型时无法将
``model_validator`` 抛出的 ``ValueError`` 转换为 422 响应的限制。
"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.constants import (
    DEFAULT_FOLLOW_LINK,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_PAGE,
    MIN_PAGE_SIZE,
)
from app.schemas.base import BaseSchema
from app.schemas.filesystem import DirectoryFilterType


class SearchQuery(BaseSchema):
    """搜索接口的查询参数模型。

    所有过滤条件都是可选的，缺省时仅按 ``path`` 递归遍历所有条目。
    多个条件之间为「与」关系。
    """

    q: Optional[str] = Field(
        description="文件名关键词，不区分大小写的子串匹配；为空时不过滤名称",
        default=None,
    )

    path: str = Field(
        description="搜索起始目录的沙箱虚拟路径，默认为根目录",
        default="/",
    )

    type: DirectoryFilterType = Field(
        description="过滤类型：all / file / directory",
        default="all",
    )

    min_size: Optional[int] = Field(
        description="最小字节数（含）",
        default=None,
        ge=0,
    )

    max_size: Optional[int] = Field(
        description="最大字节数（含）",
        default=None,
        ge=0,
    )

    modified_after: Optional[datetime] = Field(
        description="修改时间下限（含），ISO 8601 时间，naive 时间视为 UTC",
        default=None,
    )

    modified_before: Optional[datetime] = Field(
        description="修改时间上限（含），ISO 8601 时间，naive 时间视为 UTC",
        default=None,
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

    follow_link: bool = Field(
        description="是否跟随符号链接；为 false 时符号链接以 link 返回",
        default=DEFAULT_FOLLOW_LINK,
    )


__all__ = ["SearchQuery"]
