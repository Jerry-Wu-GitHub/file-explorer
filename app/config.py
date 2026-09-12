"""项目全局配置模块。

本模块定义 :class:`Config` 单例数据类，并通过 :func:`get_config`
提供全局访问入口。所有配置项均支持通过环境变量（包括项目根目录下
的 ``.env`` 文件）覆盖，环境变量名与 :mod:`app.constants` 中的常量
同名，例如 ``HOST``、``PORT``、``SANDBOX_ROOT`` 等。

环境变量解析规则：

- 字符串类型：使用 ``os.getenv`` 原值；未设置或空字符串时使用默认值。
- 整数类型：解析失败时回退到默认值。
- 布尔类型：``1`` / ``true`` / ``yes`` / ``on``（大小写不敏感）视为真，
  其余非空字符串视为假。
- 路径类型：会展开 ``~`` 并解析为绝对路径。
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .constants import (
    API_PREFIX,
    CORS_ALLOWED_ORIGINS,
    DEFAULT_ACCENT_COLOR,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_FOLLOW_LINK,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_THEME,
    HOST,
    MAX_CHUNKS,
    MAX_CHUNK_SIZE,
    MAX_CONCURRENT_UPLOAD_SESSIONS,
    MAX_PAGE_SIZE,
    MAX_UPLOAD_SIZE,
    MIN_CHUNK_SIZE,
    PORT,
    REQUEST_ID_HEADER,
    SANDBOX_ROOT,
    SERVE_STATIC_FILES,
    STATIC_DIRECTORY,
    STATIC_PREFIX,
    UPLOAD_CLEANUP_INTERVAL_SECONDS,
    UPLOAD_DATABASE_PATH,
    UPLOAD_SESSION_TTL_SECONDS,
    UPLOAD_TEMP_ROOT,
)


# 在模块首次导入时加载项目根目录下的 .env 文件。
load_dotenv()


def read_environment_string(name: str, default: str) -> str:
    """从环境变量读取字符串值。

    Args:
        name: 环境变量名。
        default: 环境变量未设置或为空字符串时返回的默认值。

    Returns:
        环境变量对应的字符串值；若环境变量未设置或为空则返回默认值。
    """
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def read_environment_int(name: str, default: int) -> int:
    """从环境变量读取整数值。

    Args:
        name: 环境变量名。
        default: 环境变量未设置、为空或解析失败时返回的默认值。

    Returns:
        解析后的整数值；无法解析时返回默认值。
    """
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def read_environment_bool(name: str, default: bool) -> bool:
    """从环境变量读取布尔值。

    可识别的真值为 ``1``、``true``、``yes``、``on``（大小写不敏感），
    其余非空字符串均视为 ``False``。

    Args:
        name: 环境变量名。
        default: 环境变量未设置或为空时返回的默认值。

    Returns:
        解析后的布尔值；无法识别时返回默认值。
    """
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def read_environment_path(name: str, default: str | Path) -> Path:
    """从环境变量读取路径并解析为绝对路径。

    Args:
        name: 环境变量名。
        default: 环境变量未设置或为空时使用的默认路径。

    Returns:
        展开 ``~`` 并解析后的绝对路径对象。
    """
    raw_path = read_environment_string(name, default)
    return Path(raw_path).expanduser().resolve()


# 模块加载时统一解析一次环境变量，作为 Config 各字段的默认值。
_HOST = read_environment_string("HOST", HOST)
_PORT = read_environment_int("PORT", PORT)
_CORS_ALLOWED_ORIGINS = read_environment_string(
    "CORS_ALLOWED_ORIGINS", CORS_ALLOWED_ORIGINS
)
_SERVE_STATIC_FILES = read_environment_bool(
    "SERVE_STATIC_FILES", SERVE_STATIC_FILES
)
_SANDBOX_ROOT = read_environment_path("SANDBOX_ROOT", SANDBOX_ROOT)
_STATIC_DIRECTORY = read_environment_path("STATIC_DIRECTORY", STATIC_DIRECTORY)
_DEFAULT_PAGE = read_environment_int("DEFAULT_PAGE", DEFAULT_PAGE)
_DEFAULT_PAGE_SIZE = read_environment_int("DEFAULT_PAGE_SIZE", DEFAULT_PAGE_SIZE)
_MAX_PAGE_SIZE = read_environment_int("MAX_PAGE_SIZE", MAX_PAGE_SIZE)
_DEFAULT_FOLLOW_LINK = read_environment_bool(
    "DEFAULT_FOLLOW_LINK", DEFAULT_FOLLOW_LINK
)
_UPLOAD_TEMP_ROOT = read_environment_path("UPLOAD_TEMP_ROOT", UPLOAD_TEMP_ROOT)
_UPLOAD_DATABASE_PATH = read_environment_path(
    "UPLOAD_DATABASE_PATH", UPLOAD_DATABASE_PATH
)
_DEFAULT_CHUNK_SIZE = read_environment_int(
    "DEFAULT_CHUNK_SIZE", DEFAULT_CHUNK_SIZE
)
_MIN_CHUNK_SIZE = read_environment_int("MIN_CHUNK_SIZE", MIN_CHUNK_SIZE)
_MAX_CHUNK_SIZE = read_environment_int("MAX_CHUNK_SIZE", MAX_CHUNK_SIZE)
_MAX_CHUNKS = read_environment_int("MAX_CHUNKS", MAX_CHUNKS)
_MAX_UPLOAD_SIZE = read_environment_int("MAX_UPLOAD_SIZE", MAX_UPLOAD_SIZE)
_UPLOAD_SESSION_TTL_SECONDS = read_environment_int(
    "UPLOAD_SESSION_TTL_SECONDS", UPLOAD_SESSION_TTL_SECONDS
)
_MAX_CONCURRENT_UPLOAD_SESSIONS = read_environment_int(
    "MAX_CONCURRENT_UPLOAD_SESSIONS", MAX_CONCURRENT_UPLOAD_SESSIONS
)
_UPLOAD_CLEANUP_INTERVAL_SECONDS = read_environment_int(
    "UPLOAD_CLEANUP_INTERVAL_SECONDS", UPLOAD_CLEANUP_INTERVAL_SECONDS
)
_DEFAULT_THEME = read_environment_string("DEFAULT_THEME", DEFAULT_THEME)
_DEFAULT_ACCENT_COLOR = read_environment_string(
    "DEFAULT_ACCENT_COLOR", DEFAULT_ACCENT_COLOR
)


@dataclass(frozen=True)
class Config:
    """项目全局配置。

    所有字段的默认值来自环境变量，环境变量未设置时回退到
    :mod:`app.constants` 中定义的常量。该类为不可变对象，
    请通过 :func:`get_config` 获取全局唯一实例。
    """

    host: str = field(
        default=_HOST,
        metadata={"description": "HTTP 服务监听地址"},
    )

    port: int = field(
        default=_PORT,
        metadata={"description": "HTTP 服务监听端口"},
    )

    api_prefix: str = field(
        default=API_PREFIX,
        metadata={"description": "业务 API 路由公共前缀"},
    )

    static_prefix: str = field(
        default=STATIC_PREFIX,
        metadata={"description": "静态资源路由公共前缀"},
    )

    request_id_header: str = field(
        default=REQUEST_ID_HEADER,
        metadata={"description": "请求追踪 ID 头部名称"},
    )

    cors_allowed_origins: str = field(
        default=_CORS_ALLOWED_ORIGINS,
        metadata={"description": "CORS 允许来源，多个来源以英文逗号分隔"},
    )

    serve_static_files: bool = field(
        default=_SERVE_STATIC_FILES,
        metadata={"description": "是否启用静态文件服务"},
    )

    sandbox_root: Path = field(
        default=_SANDBOX_ROOT,
        metadata={"description": "沙箱根目录的绝对路径"},
    )

    static_directory: Path = field(
        default=_STATIC_DIRECTORY,
        metadata={"description": "前端静态资源根目录的绝对路径"},
    )

    default_page: int = field(
        default=_DEFAULT_PAGE,
        metadata={"description": "目录列表默认页码"},
    )

    default_page_size: int = field(
        default=_DEFAULT_PAGE_SIZE,
        metadata={"description": "目录列表默认每页数量"},
    )

    max_page_size: int = field(
        default=_MAX_PAGE_SIZE,
        metadata={"description": "目录列表允许的最大每页数量"},
    )

    default_follow_link: bool = field(
        default=_DEFAULT_FOLLOW_LINK,
        metadata={"description": "默认是否跟随符号链接"},
    )

    upload_temp_root: Path = field(
        default=_UPLOAD_TEMP_ROOT,
        metadata={"description": "分片上传临时根目录的绝对路径"},
    )

    upload_database_path: Path = field(
        default=_UPLOAD_DATABASE_PATH,
        metadata={"description": "分片上传会话元数据 SQLite 数据库文件路径"},
    )

    default_chunk_size: int = field(
        default=_DEFAULT_CHUNK_SIZE,
        metadata={"description": "分片上传默认分片大小（字节）"},
    )

    min_chunk_size: int = field(
        default=_MIN_CHUNK_SIZE,
        metadata={"description": "分片上传允许的最小分片大小（字节）"},
    )

    max_chunk_size: int = field(
        default=_MAX_CHUNK_SIZE,
        metadata={"description": "分片上传允许的最大分片大小（字节）"},
    )

    max_chunks: int = field(
        default=_MAX_CHUNKS,
        metadata={"description": "单个上传会话允许的最大分片数量"},
    )

    max_upload_size: int = field(
        default=_MAX_UPLOAD_SIZE,
        metadata={"description": "单个文件允许的最大字节数"},
    )

    upload_session_ttl_seconds: int = field(
        default=_UPLOAD_SESSION_TTL_SECONDS,
        metadata={"description": "上传会话有效期（秒）"},
    )

    max_concurrent_upload_sessions: int = field(
        default=_MAX_CONCURRENT_UPLOAD_SESSIONS,
        metadata={"description": "同时允许存在的最大上传会话数"},
    )

    upload_cleanup_interval_seconds: int = field(
        default=_UPLOAD_CLEANUP_INTERVAL_SECONDS,
        metadata={"description": "过期上传会话后台清理任务的执行周期（秒）"},
    )

    default_theme: str = field(
        default=_DEFAULT_THEME,
        metadata={"description": "前端默认主题，可选 light / dark / system"},
    )

    default_accent_color: str = field(
        default=_DEFAULT_ACCENT_COLOR,
        metadata={"description": "前端默认强调色，十六进制颜色字符串"},
    )


@lru_cache(maxsize=1)
def get_config() -> Config:
    """获取全局唯一的 :class:`Config` 实例。

    该函数通过 :func:`functools.lru_cache` 保证进程内仅创建一次配置
    对象，多次调用返回同一个实例，避免重复读取环境变量。

    Returns:
        全局配置单例。
    """
    return Config()
