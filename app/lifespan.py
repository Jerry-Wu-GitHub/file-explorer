"""
本模块负责：

- 确保运行时目录（沙箱根目录、分片上传临时根目录）存在；
- 注册请求追踪 ID 中间件与 CORS 中间件；
- 注册全局异常处理器；
- 注册业务 API 与静态文件路由；
- 在应用启动时启动分片上传的后台清理任务，关闭时优雅停止。
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .config import get_config
from .dependencies.services import get_upload_cleanup_service
from .middleware import RequestIdMiddleware
from .services.upload_cleanup_service import (
    CLEANUP_SHUTDOWN_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)


def parse_cors_origins(raw_origins: str) -> list[str]:
    """解析 CORS 允许来源配置字符串。..."""
    stripped = raw_origins.strip()
    if stripped == "*":
        return ["*"]
    return [origin.strip() for origin in stripped.split(",") if origin.strip()]


def ensure_runtime_directories() -> None:
    """确保运行时所需的目录存在。..."""
    config = get_config()
    config.sandbox_root.mkdir(parents=True, exist_ok=True)
    config.upload_temp_root.mkdir(parents=True, exist_ok=True)


def register_middlewares(application: FastAPI) -> None:
    """在 FastAPI 应用上注册中间件。..."""
    config = get_config()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=parse_cors_origins(config.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[config.request_id_header],
    )
    application.add_middleware(RequestIdMiddleware)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期钩子。"""
    # 配置 FastAPI 应用实例
    config = get_config()
    ensure_runtime_directories()
    logger.info(
        "File Explorer 应用已初始化，沙箱根目录：%s，上传临时目录：%s",
        config.sandbox_root,
        config.upload_temp_root,
    )

    # 启动上传清理任务
    cleanup_service = get_upload_cleanup_service()
    stop_event = asyncio.Event()
    cleanup_task = asyncio.create_task(
        cleanup_service.run_periodically(stop_event)
    )
    logger.info("上传清理任务已启动")

    try:
        yield
    finally:
        # 停止子进程
        stop_event.set()
        try:
            await asyncio.wait_for(
                cleanup_task,
                timeout=CLEANUP_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("上传清理任务未在超时内停止，已强制取消")
            cleanup_task.cancel()
        logger.info("上传清理任务已停止")
