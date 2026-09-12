"""统一错误模型与 FastAPI 异常处理器。

所有业务错误通过 FileExplorerError 抛出，由异常处理器统一转换为
ErrorResponse 结构，保证任何错误响应格式一致。
"""

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.common import ErrorResponse

logger = logging.getLogger("file-explorer")


class FileExplorerError(Exception):
    """业务异常基类，携带 HTTP 状态码与业务错误码。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code: int = status_code
        self.code: str = code
        self.message: str = message
        self.details: Optional[dict[str, Any]] = details


class InvalidPathError(FileExplorerError):
    """路径非法：包含 ..、~ 或格式错误。"""

    def __init__(self, message: str = "路径非法") -> None:
        super().__init__(status_code=400, code="INVALID_PATH", message=message)


class PathOutsideSandboxError(FileExplorerError):
    """真实路径越出沙箱根目录（分片上传接口使用）。"""

    def __init__(self, message: str = "路径越出沙箱根目录") -> None:
        super().__init__(
            status_code=403, code="PATH_OUTSIDE_SANDBOX", message=message
        )


class ForbiddenError(FileExplorerError):
    """权限不足或路径越出沙箱（通用接口使用）。"""

    def __init__(self, message: str = "操作被拒绝") -> None:
        super().__init__(status_code=403, code="FORBIDDEN", message=message)


class NotFoundError(FileExplorerError):
    """文件或目录不存在。"""

    def __init__(self, message: str = "文件或目录不存在") -> None:
        super().__init__(status_code=404, code="NOT_FOUND", message=message)


class ParentNotFoundError(FileExplorerError):
    """目标父目录不存在。"""

    def __init__(self, message: str = "父目录不存在") -> None:
        super().__init__(status_code=404, code="PARENT_NOT_FOUND", message=message)


class ConflictError(FileExplorerError):
    """目标已存在且不允许覆盖等冲突。"""

    def __init__(self, message: str = "目标已存在", details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(status_code=409, code="CONFLICT", message=message, details=details)


class ValidationFailedError(FileExplorerError):
    """请求参数校验失败。"""

    def __init__(self, message: str = "请求参数校验失败", details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            status_code=422, code="VALIDATION_ERROR", message=message, details=details
        )


class PayloadTooLargeError(FileExplorerError):
    """上传内容超过大小限制。"""

    def __init__(self, message: str = "上传内容超过大小限制") -> None:
        super().__init__(status_code=413, code="PAYLOAD_TOO_LARGE", message=message)


class RangeNotSatisfiableError(FileExplorerError):
    """HTTP Range 请求范围无效。"""

    def __init__(self, message: str = "范围请求不满足", details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            status_code=416, code="RANGE_NOT_SATISFIABLE", message=message, details=details
        )


class UploadNotFoundError(FileExplorerError):
    """上传会话不存在。"""

    def __init__(self, message: str = "上传会话不存在") -> None:
        super().__init__(status_code=404, code="UPLOAD_NOT_FOUND", message=message)


class UploadExpiredError(FileExplorerError):
    """上传会话已过期。"""

    def __init__(self, message: str = "上传会话已过期") -> None:
        super().__init__(status_code=410, code="UPLOAD_EXPIRED", message=message)


class UploadConflictError(FileExplorerError):
    """上传会话状态冲突（已取消、已完成、合并中等）。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, code=code, message=message)


class ChecksumMismatchError(FileExplorerError):
    """分片或整体校验失败。"""

    def __init__(self, message: str = "校验值不匹配") -> None:
        super().__init__(status_code=422, code="CHECKSUM_MISMATCH", message=message)


class InsufficientStorageError(FileExplorerError):
    """磁盘剩余空间不足。"""

    def __init__(self, message: str = "磁盘剩余空间不足") -> None:
        super().__init__(status_code=507, code="INSUFFICIENT_STORAGE", message=message)


class InternalError(FileExplorerError):
    """服务端内部错误。"""

    def __init__(self, message: str = "服务端内部错误") -> None:
        super().__init__(status_code=500, code="INTERNAL_ERROR", message=message)


def _error_response(
    status_code: int, code: str, message: str, details: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """构造统一错误响应体。"""
    return ErrorResponse(
        code=code,
        message=message,
        details=details,
    ).model_dump(by_alias=True)


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册统一异常处理器。"""

    @app.exception_handler(FileExplorerError)
    async def handle_file_explorer_error(
        request: Request, exc: FileExplorerError
    ) -> JSONResponse:
        """处理业务异常。"""
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_response(exc.status_code, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """将 FastAPI 参数校验错误统一为 VALIDATION_ERROR。"""
        details = {"errors": _serializable_validation_errors(exc.errors())}
        return JSONResponse(
            status_code=422,
            content=_error_response(422, "VALIDATION_ERROR", "请求参数校验失败", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """将 Starlette 原生 HTTP 异常统一为 ErrorResponse 格式。"""
        code = _code_for_status(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_response(exc.status_code, code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """兜底处理未预期异常，避免泄漏内部细节。"""
        logger.exception("未预期异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_error_response(500, "INTERNAL_ERROR", "服务端内部错误"),
        )


def _serializable_validation_errors(errors: list[Any]) -> list[dict[str, Any]]:
    """将 Pydantic 校验错误转换为可 JSON 序列化的结构。"""
    cleaned: list[dict[str, Any]] = []
    for error in errors:
        item: dict[str, Any] = {
            "loc": list(error.get("loc", [])),
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        cleaned.append(item)
    return cleaned


def _code_for_status(status_code: int) -> str:
    """根据 HTTP 状态码映射通用业务错误码。"""
    mapping: dict[int, str] = {
        400: "INVALID_PATH",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        416: "RANGE_NOT_SATISFIABLE",
        422: "VALIDATION_ERROR",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_ERROR",
    }
    return mapping.get(status_code, "HTTP_ERROR")
