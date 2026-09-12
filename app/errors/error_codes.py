"""业务错误码定义。

本模块集中定义所有业务错误码，供
:class:`app.errors.exceptions.BusinessError` 与统一错误处理器使用。
错误码继承自 ``str`` 与 ``Enum``，既可直接作为字符串比较与序列化，
又可作为枚举成员使用。
"""

from enum import Enum


class ErrorCode(str, Enum):
    """业务错误码枚举。

    成员对应一个语义化的大写字符串。HTTP 状态码的映射由
    :data:`app.errors.exceptions.ERROR_CODE_HTTP_STATUS` 定义。
    """

    # 路径非法，例如包含 ..、~ 或格式错误
    INVALID_PATH = "INVALID_PATH"

    # 分片大小不符合预期
    INVALID_CHUNK_SIZE = "INVALID_CHUNK_SIZE"

    # 真实路径越出沙箱根目录
    PATH_OUTSIDE_SANDBOX = "PATH_OUTSIDE_SANDBOX"

    # 权限不足
    FORBIDDEN = "FORBIDDEN"

    # 文件或目录不存在
    NOT_FOUND = "NOT_FOUND"

    # 目录非空，无法在非递归模式下删除
    DIRECTORY_NOT_EMPTY = "DIRECTORY_NOT_EMPTY"

    # 上传会话不存在
    UPLOAD_NOT_FOUND = "UPLOAD_NOT_FOUND"

    # 目标父目录不存在
    PARENT_NOT_FOUND = "PARENT_NOT_FOUND"

    # 目标文件已存在且不允许覆盖
    FILE_EXISTS = "FILE_EXISTS"

    # 通用冲突，已存在且不允许覆盖
    CONFLICT = "CONFLICT"

    # 分片未全部上传
    UPLOAD_INCOMPLETE = "UPLOAD_INCOMPLETE"

    # 上传已完成
    UPLOAD_ALREADY_COMPLETED = "UPLOAD_ALREADY_COMPLETED"

    # 上传正在合并
    UPLOAD_COMPLETING = "UPLOAD_COMPLETING"

    # 上传已取消
    UPLOAD_CANCELED = "UPLOAD_CANCELED"

    # 上传会话已过期
    UPLOAD_EXPIRED = "UPLOAD_EXPIRED"

    # 文件或分片超过大小限制
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

    # 分片编号越界
    CHUNK_OUT_OF_RANGE = "CHUNK_OUT_OF_RANGE"

    # HTTP Range 请求非法
    RANGE_NOT_SATISFIABLE = "RANGE_NOT_SATISFIABLE"

    # 请求参数校验失败
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # 分片或整体校验失败
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"

    # 磁盘空间不足
    INSUFFICIENT_STORAGE = "INSUFFICIENT_STORAGE"

    # 服务端内部错误
    INTERNAL_ERROR = "INTERNAL_ERROR"

    def __str__(self) -> str:
        """返回错误码的字符串值，便于直接拼接到日志与响应体中。"""
        return self.value


__all__ = ["ErrorCode"]
