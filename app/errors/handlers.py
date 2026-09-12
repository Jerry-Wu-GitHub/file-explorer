"""全局异常处理器。

本模块注册统一异常处理器，保证所有失败响应都使用
:class:`app.routes.schemas.base.ErrorResponse` 格式，不混用
FastAPI 默认错误格式。

处理器覆盖四类失败来源：

- 业务层主动抛出的 :class:`BusinessError`；
- FastAPI 请求参数校验失败 :class:`RequestValidationError`；
- Starlette 抛出的 :class:`HTTPException`（404 路由未命中、405 等）；
- 未捕获的通用异常，兜底为 ``INTERNAL_ERROR``。
"""

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.errors.error_codes import ErrorCode
from app.errors.exceptions import (
    BusinessError,
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_CONFLICT,
    HTTP_STATUS_CONTENT_TOO_LARGE,
    HTTP_STATUS_FORBIDDEN,
    HTTP_STATUS_GONE,
    HTTP_STATUS_INSUFFICIENT_STORAGE,
    HTTP_STATUS_INTERNAL_SERVER_ERROR,
    HTTP_STATUS_NOT_FOUND,
    HTTP_STATUS_RANGE_NOT_SATISFIABLE,
    HTTP_STATUS_UNPROCESSABLE_CONTENT,
)
from app.schemas.base import ErrorResponse

logger = logging.getLogger(__name__)


def read_request_id(request: Request) -> Optional[str]:
    """从请求状态中读取请求追踪 ID。

    请求 ID 由 ``RequestIdMiddleware`` 注入到 ``request.state``，
    若中间件未启用则返回 ``None``。

    Args:
        request: 当前请求对象。

    Returns:
        请求追踪 ID；不可用时返回 ``None``。
    """
    return getattr(request.state, "request_id", None)


def build_error_response(
    code: str,
    message: str,
    request: Request,
    http_status: int,
    details: Optional[dict[str, Any]] = None,
) -> JSONResponse:
    """构造统一的错误响应。

    Args:
        code: 业务错误码字符串。
        message: 人类可读的错误提示文案。
        request: 当前请求对象，用于提取请求 ID。
        http_status: HTTP 状态码。
        details: 附加详情，默认为 ``None``。

    Returns:
        序列化后的 :class:`ErrorResponse` JSON 响应。
    """
    payload = ErrorResponse(
        code=code,
        message=message,
        details=details,
        request_id=read_request_id(request),
    )
    return JSONResponse(
        status_code=http_status,
        content=payload.model_dump(by_alias=True),
    )


def map_http_status_to_error_code(http_status: int) -> ErrorCode:
    """将 HTTP 状态码映射为兜底业务错误码。

    用于 :class:`HTTPException` 场景，例如路由未命中返回 404 时，
    需要一个与之语义匹配的业务错误码。

    Args:
        http_status: HTTP 状态码。

    Returns:
        与状态码语义最接近的业务错误码。
    """
    if http_status == HTTP_STATUS_BAD_REQUEST:
        return ErrorCode.VALIDATION_ERROR
    if http_status == HTTP_STATUS_FORBIDDEN:
        return ErrorCode.FORBIDDEN
    if http_status == HTTP_STATUS_NOT_FOUND:
        return ErrorCode.NOT_FOUND
    if http_status == HTTP_STATUS_CONFLICT:
        return ErrorCode.CONFLICT
    if http_status == HTTP_STATUS_GONE:
        return ErrorCode.UPLOAD_EXPIRED
    if http_status == HTTP_STATUS_CONTENT_TOO_LARGE:
        return ErrorCode.PAYLOAD_TOO_LARGE
    if http_status == HTTP_STATUS_RANGE_NOT_SATISFIABLE:
        return ErrorCode.RANGE_NOT_SATISFIABLE
    if http_status == HTTP_STATUS_UNPROCESSABLE_CONTENT:
        return ErrorCode.VALIDATION_ERROR
    if http_status == HTTP_STATUS_INSUFFICIENT_STORAGE:
        return ErrorCode.INSUFFICIENT_STORAGE
    return ErrorCode.INTERNAL_ERROR


async def handle_business_error(
    request: Request,
    exc: BusinessError,
) -> JSONResponse:
    """处理业务异常 :class:`BusinessError`。

    Args:
        request: 当前请求对象。
        exc: 业务异常实例。

    Returns:
        与异常中错误码对应的统一错误响应。
    """
    return build_error_response(
        code=exc.code.value,
        message=exc.message,
        request=request,
        http_status=exc.http_status,
        details=exc.details,
    )


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """处理 FastAPI 请求参数校验失败。

    Args:
        request: 当前请求对象。
        exc: 参数校验异常。

    Returns:
        ``422 VALIDATION_ERROR`` 统一错误响应。
    """
    return build_error_response(
        code=ErrorCode.VALIDATION_ERROR.value,
        message="请求参数校验失败",
        request=request,
        http_status=HTTP_STATUS_UNPROCESSABLE_CONTENT,
        details={"errors": exc.errors()},
    )


async def handle_http_exception(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """处理 Starlette / FastAPI 抛出的 :class:`HTTPException`。

    Args:
        request: 当前请求对象。
        exc: HTTP 异常实例。

    Returns:
        与状态码语义匹配的统一错误响应。
    """
    error_code = map_http_status_to_error_code(exc.status_code)
    return build_error_response(
        code=error_code.value,
        message=str(exc.detail),
        request=request,
        http_status=exc.status_code,
    )


async def handle_uncaught_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """处理未捕获异常，兜底返回 ``500 INTERNAL_ERROR``。

    Args:
        request: 当前请求对象。
        exc: 未捕获异常实例。

    Returns:
        ``500 INTERNAL_ERROR`` 统一错误响应。
    """
    logger.exception("未捕获异常：%s", exc)
    return build_error_response(
        code=ErrorCode.INTERNAL_ERROR.value,
        message="服务端内部错误",
        request=request,
        http_status=HTTP_STATUS_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI 应用上注册所有全局异常处理器。

    Args:
        app: FastAPI 应用实例。
    """
    app.add_exception_handler(BusinessError, handle_business_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_uncaught_exception)


__all__ = [
    "register_exception_handlers",
    "build_error_response",
    "map_http_status_to_error_code",
]
