"""分片上传相关的常量定义。

本模块定义分片上传所需的分片大小、分片数量、文件大小、
会话有效期、并发会话数、状态机取值、校验算法等常量。
"""

from pathlib import Path

# 分片上传临时根目录，必须位于沙箱之外，不对外暴露
UPLOAD_TEMP_ROOT: Path = Path("./.upload_tmp")

# 分片上传会话元数据 SQLite 数据库文件路径
UPLOAD_DATABASE_PATH: Path = Path("./.upload_tmp/uploads.sqlite3")

# 默认分片大小（16 MiB）
DEFAULT_CHUNK_SIZE: int = 16 * 1024 * 1024

# 允许的最小分片大小（256 KiB）
MIN_CHUNK_SIZE: int = 256 * 1024

# 允许的最大分片大小（256 MiB）
MAX_CHUNK_SIZE: int = 256 * 1024 * 1024

# 单个上传会话允许的最大分片数量
MAX_CHUNKS: int = 10000

# 单个文件允许的最大字节数（20 GiB）
MAX_UPLOAD_SIZE: int = 20 * 1024 * 1024 * 1024

# 上传会话默认有效期（秒），默认 24 小时
UPLOAD_SESSION_TTL_SECONDS: int = 24 * 60 * 60

# 服务端允许同时存在的最大上传会话数
MAX_CONCURRENT_UPLOAD_SESSIONS: int = 128

# 过期上传会话后台清理任务的执行周期（秒）
UPLOAD_CLEANUP_INTERVAL_SECONDS: int = 10 * 60

# 初始化与合并时预留的磁盘安全余量（字节）
UPLOAD_STORAGE_SAFETY_MARGIN_BYTES: int = 64 * 1024 * 1024

# 上传会话状态：已初始化但尚未上传任何分片
STATUS_CREATED: str = "created"

# 上传会话状态：至少上传了一个分片但尚未完成
STATUS_UPLOADING: str = "uploading"

# 上传会话状态：正在合并分片，拒绝新的分片上传
STATUS_COMPLETING: str = "completing"

# 上传会话状态：已完成合并，目标文件已生成
STATUS_COMPLETED: str = "completed"

# 上传会话状态：客户端已取消
STATUS_CANCELED: str = "canceled"

# 上传会话状态：已超过有效期
STATUS_EXPIRED: str = "expired"

# 上传会话状态：因内部错误或恢复失败而不可继续
STATUS_FAILED: str = "failed"

# 已上传分片文件使用的后缀
CHUNK_FILE_SUFFIX: str = ".part"

# 分片写入过程中的中间临时文件后缀
CHUNK_TEMP_SUFFIX: str = ".part.tmp"

# 合并过程中目标目录临时文件使用的后缀
MERGE_TEMP_SUFFIX: str = ".merging"

# 分片/整体校验使用的 SHA-256 算法名
CHECKSUM_ALGORITHM_SHA256: str = "sha256"

# 分片校验使用的 MD5 算法名
CHECKSUM_ALGORITHM_MD5: str = "md5"

# 支持的整体/分片校验算法集合
SUPPORTED_CHECKSUM_ALGORITHMS: tuple[str, ...] = (
    CHECKSUM_ALGORITHM_SHA256,
    CHECKSUM_ALGORITHM_MD5,
)

# 分片上传时可选携带的 MD5 校验头部
HEADER_CONTENT_MD5: str = "Content-MD5"

# 分片上传时可选携带的 SHA-256 校验头部
HEADER_CHUNK_SHA256: str = "X-Chunk-SHA256"

__all__ = [
    "UPLOAD_TEMP_ROOT",
    "UPLOAD_DATABASE_PATH",
    "DEFAULT_CHUNK_SIZE",
    "MIN_CHUNK_SIZE",
    "MAX_CHUNK_SIZE",
    "MAX_CHUNKS",
    "MAX_UPLOAD_SIZE",
    "UPLOAD_SESSION_TTL_SECONDS",
    "MAX_CONCURRENT_UPLOAD_SESSIONS",
    "UPLOAD_CLEANUP_INTERVAL_SECONDS",
    "UPLOAD_STORAGE_SAFETY_MARGIN_BYTES",
    "STATUS_CREATED",
    "STATUS_UPLOADING",
    "STATUS_COMPLETING",
    "STATUS_COMPLETED",
    "STATUS_CANCELED",
    "STATUS_EXPIRED",
    "STATUS_FAILED",
    "CHUNK_FILE_SUFFIX",
    "CHUNK_TEMP_SUFFIX",
    "MERGE_TEMP_SUFFIX",
    "CHECKSUM_ALGORITHM_SHA256",
    "CHECKSUM_ALGORITHM_MD5",
    "SUPPORTED_CHECKSUM_ALGORITHMS",
    "HEADER_CONTENT_MD5",
    "HEADER_CHUNK_SHA256",
]
