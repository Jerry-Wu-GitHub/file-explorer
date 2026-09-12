"""应用入口模块。

本模块负责：

- 创建 FastAPI 应用实例；
- 确保运行时目录（沙箱根目录、分片上传临时根目录）存在；
- 注册请求追踪 ID 中间件与 CORS 中间件；
- 注册全局异常处理器；
- 注册业务 API 与静态文件路由；
- 在应用启动时启动分片上传的后台清理任务，关闭时优雅停止。

对外暴露的 ``app`` 供 ``uvicorn main:app`` 引用。
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from app.config import get_config
from app.dependencies.services import get_upload_cleanup_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes import get_router
from app.routes.static import mount_static_files
from app.services.upload_cleanup_service import (
    CLEANUP_SHUTDOWN_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期钩子。..."""
    del application
    cleanup_service = get_upload_cleanup_service()
    stop_event = asyncio.Event()
    cleanup_task = asyncio.create_task(
        cleanup_service.run_periodically(stop_event)
    )
    logger.info("上传清理任务已启动")
    try:
        yield
    finally:
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


def create_application() -> FastAPI:
    """创建并完整配置 FastAPI 应用实例。..."""
    config = get_config()
    application = FastAPI(
        title="File Explorer API",
        description=(
            "文件资源管理器服务后端，提供文件访问、修改、删除、"
            "上传、下载等能力。"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    ensure_runtime_directories()
    register_middlewares(application)
    register_exception_handlers(application)
    mount_static_files(application)
    application.include_router(get_router())
    logger.info(
        "File Explorer 应用已初始化，沙箱根目录：%s，上传临时目录：%s",
        config.sandbox_root,
        config.upload_temp_root,
    )
    return application


app = create_application()
"""ASGI 应用实例，供 ``uvicorn main:app`` 引用。"""


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=7860)
