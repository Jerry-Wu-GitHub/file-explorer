"""上传临时数据的后台清理任务。"""

import asyncio
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from app.config import get_config
from app.constants.uploads import UPLOAD_CLEANUP_INTERVAL_SECONDS
from app.models.upload_session import UploadSession
from app.utils.errors import UploadNotFoundError
from app.utils.uploads import session_store

logger = logging.getLogger("file-explorer")

_ZIP_DIR_NAME: str = "zip"
_ZIP_MAX_AGE_SECONDS: int = 3600


def cleanup_expired_sessions() -> None:
    """扫描并清理过期会话的分片与元数据，同时清理孤儿分片目录。"""
    now: float = time.time()
    active_ids: set[str] = set()

    for upload_id in session_store.list_session_ids():
        try:
            session: UploadSession = session_store.load_session(upload_id)
        except UploadNotFoundError:
            continue

        if now > session.expires_at:
            session_store.delete_chunk_dir(upload_id)
            session_store.delete_session_file(upload_id)
            logger.info("清理过期上传会话: %s", upload_id)
        else:
            active_ids.add(upload_id)

    _cleanup_orphan_chunk_dirs(active_ids)
    _cleanup_old_zip_files()


def _cleanup_orphan_chunk_dirs(active_ids: set[str]) -> None:
    """删除没有对应会话元数据的分片目录。"""
    _, chunk_root = session_store.ensure_upload_dirs()
    for directory in chunk_root.iterdir():
        if not directory.is_dir():
            continue
        if directory.name not in active_ids:
            shutil.rmtree(directory, ignore_errors=True)
            logger.info("清理孤儿分片目录: %s", directory.name)


def _cleanup_old_zip_files() -> None:
    """清理超过保留期的临时 zip 文件。"""
    zip_dir: Path = Path(get_config().upload_temp_root) / _ZIP_DIR_NAME
    if not zip_dir.exists():
        return
    now: float = time.time()
    for file_path in zip_dir.iterdir():
        if not file_path.is_file():
            continue
        try:
            age_seconds: float = now - file_path.stat().st_mtime
        except OSError:
            continue
        if age_seconds > _ZIP_MAX_AGE_SECONDS:
            file_path.unlink(missing_ok=True)


async def run_cleanup_loop(stop_event: asyncio.Event) -> None:
    """周期性执行清理的后台协程，收到停止事件后退出。"""
    while not stop_event.is_set():
        try:
            cleanup_expired_sessions()
        except Exception:
            logger.exception("后台清理任务执行失败")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=UPLOAD_CLEANUP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
