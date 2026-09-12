"""请求追踪 ID 中间件。

本模块定义 :class:`RequestIdMiddleware`，为每个 HTTP 请求生成或复用
一个请求追踪 ID，并写入 ``request.state.request_id``，供业务代码与
异常处理器使用。响应完成后会把该 ID 回写到响应头，便于端到端追踪。
"""

import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..constants import REQUEST_ID_HEADER


def generate_request_id() -> str:
    """生成一个新的请求追踪 ID。

    Returns:
        使用 UUIDv4 生成的 32 位十六进制字符串。
    """
    return uuid.uuid4().hex


def extract_request_id(request: Request) -> str:
    """从请求头中读取请求追踪 ID，缺失时生成新的 ID。

    Args:
        request: 当前请求对象。

    Returns:
        客户端传入的请求 ID（若存在），否则为新生成的 ID。
    """
    header_value = request.headers.get(REQUEST_ID_HEADER)
    if header_value is None or header_value.strip() == "":
        return generate_request_id()
    return header_value.strip()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求注入并回写追踪 ID 的中间件。

    处理流程：

    1. 从请求头读取 ``X-Request-ID``，若缺失则使用 UUIDv4 生成。
    2. 将 ID 写入 ``request.state.request_id``，供业务与异常处理器访问。
    3. 调用下游应用处理请求。
    4. 将 ID 回写到响应头，无论成功或失败。
    """

    def __init__(self, app: ASGIApp) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
        """
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """处理单个请求。

        Args:
            request: 当前请求对象。
            call_next: 调用下游应用的异步函数。

        Returns:
            下游应用返回的响应，已附加请求追踪 ID 响应头。
        """
        request_id = extract_request_id(request)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


__all__ = ["RequestIdMiddleware", "generate_request_id", "extract_request_id"]
