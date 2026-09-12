"""应用全局配置。

Config 是唯一配置来源：字段默认值来自 app.constants，可通过环境变量或 .env 覆盖。
通过 get_config() 获取进程内单例。
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import paths, pagination, uploads


class Config(BaseSettings):
    """应用全局配置，字段名大写即为对应环境变量名。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = Field(
        description="应用监听端口",
        default=8000,
    )

    sandbox_root: str = Field(
        description="沙箱根目录绝对或相对路径，所有文件操作都限定在该目录内",
        default=paths.DEFAULT_SANDBOX_ROOT,
    )

    static_dir: str = Field(
        description="前端静态资源根目录",
        default=paths.STATIC_DIR,
    )

    upload_temp_root: str = Field(
        description="分片上传临时根目录，必须位于沙箱之外，禁止被文件接口访问",
        default=paths.DEFAULT_UPLOAD_TEMP_ROOT,
    )

    default_chunk_size: int = Field(
        description="分片上传默认分片大小（字节）",
        default=uploads.DEFAULT_CHUNK_SIZE,
        ge=uploads.MIN_CHUNK_SIZE,
        le=uploads.MAX_CHUNK_SIZE,
    )

    min_chunk_size: int = Field(
        description="分片上传最小分片大小（字节）",
        default=uploads.MIN_CHUNK_SIZE,
        ge=1,
    )

    max_chunk_size: int = Field(
        description="分片上传最大分片大小（字节）",
        default=uploads.MAX_CHUNK_SIZE,
        ge=1,
    )

    max_upload_size: int = Field(
        description="分片上传最大文件总大小（字节）",
        default=uploads.MAX_UPLOAD_SIZE,
        ge=1,
    )

    max_chunks: int = Field(
        description="分片上传最大分片数量",
        default=uploads.MAX_CHUNKS,
        ge=1,
    )

    upload_session_ttl_seconds: int = Field(
        description="上传会话有效期（秒）",
        default=uploads.UPLOAD_SESSION_TTL_SECONDS,
        ge=1,
    )

    max_concurrent_uploads: int = Field(
        description="最大并发上传会话数",
        default=uploads.MAX_CONCURRENT_UPLOADS,
        ge=1,
    )

    default_page_size: int = Field(
        description="默认每页条目数量",
        default=pagination.DEFAULT_PAGE_SIZE,
        ge=1,
        le=pagination.MAX_PAGE_SIZE,
    )

    max_page_size: int = Field(
        description="每页条目数量上限",
        default=pagination.MAX_PAGE_SIZE,
        ge=1,
    )


_config_instance: Optional[Config] = None


def get_config() -> Config:
    """返回应用全局配置单例。"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
