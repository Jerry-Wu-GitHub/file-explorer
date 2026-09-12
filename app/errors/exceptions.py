"""业务异常定义。

本模块定义 :class:`BusinessError`，作为所有可预期业务失败的统一
异常类型。服务层通过抛出该异常来表达业务失败，路由层无需捕获，
由全局异常处理器统一转换为
:class:`app.routes.schemas.base.ErrorResponse`。

同时定义项目内部使用的 HTTP 状态码常量，避免依赖 Starlette 中
不断更名的状态码符号（例如 ``HTTP_422_UNPROCESSABLE_ENTITY`` 已
被弃用为 ``HTTP_422_UNPROCESSABLE_CONTENT``）。
"""

from typing import Any, Optional

from ..errors.error_codes import ErrorCode


HTTP_STATUS_BAD_REQUEST: int = 400
"""HTTP 400 Bad Request。"""

HTTP_STATUS_FORBIDDEN: int = 403
"""HTTP 403 Forbidden。"""

HTTP_STATUS_NOT_FOUND: int = 404
"""HTTP 404 Not Found。"""

HTTP_STATUS_CONFLICT: int = 409
"""HTTP 409 Conflict。"""

HTTP_STATUS_GONE: int = 410
"""HTTP 410 Gone。"""

HTTP_STATUS_CONTENT_TOO_LARGE: int = 413
"""HTTP 413 Content Too Large（旧称 Payload Too Large）。"""

HTTP_STATUS_RANGE_NOT_SATISFIABLE: int = 416
"""HTTP 416 Range Not Satisfiable。"""

HTTP_STATUS_UNPROCESSABLE_CONTENT: int = 422
"""HTTP 422 Unprocessable Content（旧称 Unprocessable Entity）。"""

HTTP_STATUS_INTERNAL_SERVER_ERROR: int = 500
"""HTTP 500 Internal Server Error。"""

HTTP_STATUS_INSUFFICIENT_STORAGE: int = 507
"""HTTP 507 Insufficient Storage。"""


ERROR_CODE_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_PATH: HTTP_STATUS_BAD_REQUEST,
    ErrorCode.INVALID_CHUNK_SIZE: HTTP_STATUS_BAD_REQUEST,
    ErrorCode.PATH_OUTSIDE_SANDBOX: HTTP_STATUS_FORBIDDEN,
    ErrorCode.FORBIDDEN: HTTP_STATUS_FORBIDDEN,
    ErrorCode.NOT_FOUND: HTTP_STATUS_NOT_FOUND,
    ErrorCode.DIRECTORY_NOT_EMPTY: HTTP_STATUS_CONFLICT,
    ErrorCode.UPLOAD_NOT_FOUND: HTTP_STATUS_NOT_FOUND,
    ErrorCode.PARENT_NOT_FOUND: HTTP_STATUS_NOT_FOUND,
    ErrorCode.FILE_EXISTS: HTTP_STATUS_CONFLICT,
    ErrorCode.CONFLICT: HTTP_STATUS_CONFLICT,
    ErrorCode.UPLOAD_INCOMPLETE: HTTP_STATUS_CONFLICT,
    ErrorCode.UPLOAD_ALREADY_COMPLETED: HTTP_STATUS_CONFLICT,
    ErrorCode.UPLOAD_COMPLETING: HTTP_STATUS_CONFLICT,
    ErrorCode.UPLOAD_CANCELED: HTTP_STATUS_CONFLICT,
    ErrorCode.UPLOAD_EXPIRED: HTTP_STATUS_GONE,
    ErrorCode.PAYLOAD_TOO_LARGE: HTTP_STATUS_CONTENT_TOO_LARGE,
    ErrorCode.CHUNK_OUT_OF_RANGE: HTTP_STATUS_RANGE_NOT_SATISFIABLE,
    ErrorCode.RANGE_NOT_SATISFIABLE: HTTP_STATUS_RANGE_NOT_SATISFIABLE,
    ErrorCode.VALIDATION_ERROR: HTTP_STATUS_UNPROCESSABLE_CONTENT,
    ErrorCode.CHECKSUM_MISMATCH: HTTP_STATUS_UNPROCESSABLE_CONTENT,
    ErrorCode.INSUFFICIENT_STORAGE: HTTP_STATUS_INSUFFICIENT_STORAGE,
    ErrorCode.INTERNAL_ERROR: HTTP_STATUS_INTERNAL_SERVER_ERROR,
}
"""错误码到 HTTP 状态码的映射表。

当映射表中不存在对应条目时，兜底为 ``500 INTERNAL_SERVER_ERROR``。
"""


class BusinessError(Exception):
    """业务异常。

    所有可预期的业务失败都应抛出该异常，由全局异常处理器统一
    转换为 :class:`ErrorResponse`。不可预期的异常由兜底处理器
    转换为 ``INTERNAL_ERROR``。

    Attributes:
        code: 业务错误码。
        message: 人类可读的错误提示文案。
        http_status: 与错误码对应的 HTTP 状态码。
        details: 附加详情，可为空。
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """构造业务异常。

        Args:
            code: 业务错误码。
            message: 人类可读的错误提示文案。
            details: 附加详情，默认为 ``None``。
        """
        super().__init__(message)
        self.code: ErrorCode = code
        self.message: str = message
        self.http_status: int = ERROR_CODE_HTTP_STATUS.get(
            code,
            HTTP_STATUS_INTERNAL_SERVER_ERROR,
        )
        self.details: Optional[dict[str, Any]] = details


__all__ = [
    "BusinessError",
    "ERROR_CODE_HTTP_STATUS",
    "HTTP_STATUS_BAD_REQUEST",
    "HTTP_STATUS_FORBIDDEN",
    "HTTP_STATUS_NOT_FOUND",
    "HTTP_STATUS_CONFLICT",
    "HTTP_STATUS_GONE",
    "HTTP_STATUS_CONTENT_TOO_LARGE",
    "HTTP_STATUS_RANGE_NOT_SATISFIABLE",
    "HTTP_STATUS_UNPROCESSABLE_CONTENT",
    "HTTP_STATUS_INTERNAL_SERVER_ERROR",
    "HTTP_STATUS_INSUFFICIENT_STORAGE",
]
