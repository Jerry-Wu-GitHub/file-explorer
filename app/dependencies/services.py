"""业务服务依赖注入函数。"""

from functools import lru_cache

from ..config import get_config
from ..repositories.upload_session_repository import (
    UploadSessionRepository,
)
from ..services.archive_service import ArchiveService
from ..services.chunked_upload_service import ChunkedUploadService
from ..services.content_service import ContentService
from ..services.file_service import FileService
from ..services.metadata_service import MetadataService
from ..services.modify_service import ModifyService
from ..services.path_service import get_path_service
from ..services.search_service import SearchService
from ..services.small_file_upload_service import SmallFileUploadService
from ..services.upload_cleanup_service import UploadCleanupService
from ..services.write_service import WriteService
from ..storage.upload_chunk_storage import LocalUploadChunkStorage
from ..storage.upload_lock_manager import UploadLockManager


LOCK_DIRECTORY_NAME: str = "locks"
"""分片上传锁文件所在子目录名。"""


@lru_cache(maxsize=1)
def get_metadata_service() -> MetadataService:
    """获取 :class:`MetadataService` 单例。"""
    return MetadataService(get_path_service())


@lru_cache(maxsize=1)
def get_file_service() -> FileService:
    """获取 :class:`FileService` 单例。"""
    return FileService(get_path_service(), get_metadata_service())


@lru_cache(maxsize=1)
def get_write_service() -> WriteService:
    """获取 :class:`WriteService` 单例。"""
    return WriteService(get_path_service(), get_metadata_service())


@lru_cache(maxsize=1)
def get_modify_service() -> ModifyService:
    """获取 :class:`ModifyService` 单例。"""
    return ModifyService(get_path_service(), get_metadata_service())


@lru_cache(maxsize=1)
def get_content_service() -> ContentService:
    """获取 :class:`ContentService` 单例。"""
    return ContentService(get_path_service())


@lru_cache(maxsize=1)
def get_search_service() -> SearchService:
    """获取 :class:`SearchService` 单例。"""
    return SearchService(get_path_service(), get_metadata_service())


@lru_cache(maxsize=1)
def get_archive_service() -> ArchiveService:
    """获取 :class:`ArchiveService` 单例。"""
    return ArchiveService(get_path_service())


@lru_cache(maxsize=1)
def get_small_file_upload_service() -> SmallFileUploadService:
    """获取 :class:`SmallFileUploadService` 单例。"""
    return SmallFileUploadService(
        get_path_service(),
        get_metadata_service(),
        get_config(),
    )


@lru_cache(maxsize=1)
def get_upload_session_repository() -> UploadSessionRepository:
    """获取 :class:`UploadSessionRepository` 单例。"""
    return UploadSessionRepository(get_config().upload_database_path)


@lru_cache(maxsize=1)
def get_upload_chunk_storage() -> LocalUploadChunkStorage:
    """获取 :class:`LocalUploadChunkStorage` 单例。"""
    return LocalUploadChunkStorage(get_config().upload_temp_root)


@lru_cache(maxsize=1)
def get_upload_lock_manager() -> UploadLockManager:
    """获取 :class:`UploadLockManager` 单例。"""
    config = get_config()
    return UploadLockManager(config.upload_temp_root / LOCK_DIRECTORY_NAME)


@lru_cache(maxsize=1)
def get_chunked_upload_service() -> ChunkedUploadService:
    """获取 :class:`ChunkedUploadService` 单例。"""
    return ChunkedUploadService(
        get_path_service(),
        get_metadata_service(),
        get_upload_session_repository(),
        get_upload_chunk_storage(),
        get_upload_lock_manager(),
        get_config(),
    )


@lru_cache(maxsize=1)
def get_upload_cleanup_service() -> UploadCleanupService:
    """获取 :class:`UploadCleanupService` 单例。"""
    return UploadCleanupService(
        get_upload_session_repository(),
        get_upload_chunk_storage(),
        get_config().upload_cleanup_interval_seconds,
    )


__all__ = [
    "get_file_service",
    "get_metadata_service",
    "get_write_service",
    "get_modify_service",
    "get_content_service",
    "get_search_service",
    "get_archive_service",
    "get_small_file_upload_service",
    "get_upload_session_repository",
    "get_upload_chunk_storage",
    "get_upload_lock_manager",
    "get_chunked_upload_service",
    "get_upload_cleanup_service",
]
