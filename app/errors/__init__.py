"""错误处理包。

本包提供：

- :class:`app.errors.error_codes.ErrorCode`：业务错误码枚举；
- :class:`app.errors.exceptions.BusinessError`：业务异常；
- :data:`app.errors.exceptions.ERROR_CODE_HTTP_STATUS`：错误码到
  HTTP 状态码的映射表；
- :func:`app.errors.handlers.register_exception_handlers`：注册全局
  异常处理器的入口。
"""

from .error_codes import ErrorCode
from .exceptions import ERROR_CODE_HTTP_STATUS, BusinessError
from .handlers import register_exception_handlers

__all__ = [
    "ErrorCode",
    "BusinessError",
    "ERROR_CODE_HTTP_STATUS",
    "register_exception_handlers",
]
