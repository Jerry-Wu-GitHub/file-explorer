"""分片上传相关的默认常量，全部通过环境变量可覆盖（见 config.py）。"""

# 默认分片大小（字节）：5 MiB
DEFAULT_CHUNK_SIZE: int = 5 * 1024 * 1024

# 最小分片大小（字节）：1 MiB
MIN_CHUNK_SIZE: int = 1024 * 1024

# 最大分片大小（字节）：64 MiB
MAX_CHUNK_SIZE: int = 64 * 1024 * 1024

# 最大文件总大小（字节）：10 GiB
MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024 * 1024

# 最大分片数量
MAX_CHUNKS: int = 2048

# 上传会话默认有效期（秒）：24 小时
UPLOAD_SESSION_TTL_SECONDS: int = 24 * 60 * 60

# 最大并发上传会话数
MAX_CONCURRENT_UPLOADS: int = 128

# 会话元数据存储子目录名（位于上传临时根目录下）
UPLOAD_SESSION_DIR_NAME: str = "sessions"

# 分片文件存储子目录名（位于上传临时根目录下）
UPLOAD_CHUNKS_DIR_NAME: str = "chunks"

# 合并时单次读取的缓冲区大小（字节）
MERGE_BUFFER_SIZE: int = 4 * 1024 * 1024

# 后台过期清理任务周期（秒）
UPLOAD_CLEANUP_INTERVAL_SECONDS: int = 60

# 上传会话状态
UPLOAD_STATUS_CREATED: str = "created"
UPLOAD_STATUS_UPLOADING: str = "uploading"
UPLOAD_STATUS_COMPLETING: str = "completing"
UPLOAD_STATUS_COMPLETED: str = "completed"
UPLOAD_STATUS_CANCELED: str = "canceled"
UPLOAD_STATUS_EXPIRED: str = "expired"
