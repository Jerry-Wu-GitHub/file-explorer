"""文件系统相关的常量定义。

本模块定义沙箱、分页、排序、过滤、条目类型、隐藏项目判定
等与文件资源管理器业务直接相关的常量。
"""

SANDBOX_ROOT: str = "./sandbox"
"""沙箱根目录，所有文件 API 仅能访问该目录内的资源。"""

MIN_PAGE: int = 1
"""目录列表允许的最小页码。"""

DEFAULT_PAGE: int = 1
"""目录列表默认页码。"""

MIN_PAGE_SIZE: int = 1
"""目录列表允许的最小每页数量。"""

DEFAULT_PAGE_SIZE: int = 50
"""目录列表默认每页数量。"""

MAX_PAGE_SIZE: int = 200
"""目录列表允许的最大每页数量。"""

DEFAULT_SORT_FIELD: str = "name"
"""默认排序字段。"""

DEFAULT_SORT_ORDER: str = "asc"
"""默认排序方向。"""

SUPPORTED_SORT_FIELDS: tuple[str, ...] = (
    "name",
    "size",
    "modifiedAt",
    "createdAt",
    "accessedAt",
    "type",
)
"""支持排序的字段名集合。"""

SUPPORTED_SORT_ORDERS: tuple[str, ...] = ("asc", "desc")
"""支持的排序方向集合。"""

DEFAULT_FILTER_TYPE: str = "all"
"""目录列表默认过滤类型。"""

SUPPORTED_FILTER_TYPES: tuple[str, ...] = ("all", "file", "directory")
"""支持的过滤类型集合。"""

DEFAULT_FOLLOW_LINK: bool = True
"""默认是否跟随符号链接。"""

TYPE_FILE: str = "file"
"""条目类型：普通文件。"""

TYPE_DIRECTORY: str = "directory"
"""条目类型：目录。"""

TYPE_LINK: str = "link"
"""条目类型：符号链接。"""

TYPE_OTHER: str = "other"
"""条目类型：其它非常规文件（例如设备文件、FIFO 等）。"""

HIDDEN_FILE_PREFIX: str = "."
"""以该前缀开头的名称被视为隐藏项目。"""

ZIP_ARCHIVE_SUFFIX: str = ".zip"
"""压缩包默认后缀。"""

ZIP_CONTENT_TYPE: str = "application/zip"
"""压缩包响应的 MIME 类型。"""

ZIP_STREAM_CHUNK_SIZE: int = 1024 * 1024
"""压缩包流式写出时使用的分块大小（字节）。"""

DEFAULT_MIME_TYPE: str = "application/octet-stream"
"""无法识别时使用的默认 MIME 类型。"""

__all__ = [
    "SANDBOX_ROOT",
    "MIN_PAGE",
    "DEFAULT_PAGE",
    "MIN_PAGE_SIZE",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "DEFAULT_SORT_FIELD",
    "DEFAULT_SORT_ORDER",
    "SUPPORTED_SORT_FIELDS",
    "SUPPORTED_SORT_ORDERS",
    "DEFAULT_FILTER_TYPE",
    "SUPPORTED_FILTER_TYPES",
    "DEFAULT_FOLLOW_LINK",
    "TYPE_FILE",
    "TYPE_DIRECTORY",
    "TYPE_LINK",
    "TYPE_OTHER",
    "HIDDEN_FILE_PREFIX",
    "ZIP_ARCHIVE_SUFFIX",
    "ZIP_CONTENT_TYPE",
    "ZIP_STREAM_CHUNK_SIZE",
    "DEFAULT_MIME_TYPE",
]
