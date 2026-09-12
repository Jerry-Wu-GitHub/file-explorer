"""服务入口文件：创建 FastAPI 应用并注册路由与生命周期。"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import get_config
from app.routes import get_router
from app.utils.errors import register_exception_handlers
from app.utils.path_utils import ensure_sandbox_root
from app.utils.uploads import cleanup, session_store

logger = logging.getLogger("file-explorer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化目录与后台清理任务。"""
    ensure_sandbox_root()
    session_store.ensure_upload_dirs()
    stop_event: asyncio.Event = asyncio.Event()
    cleanup_task = asyncio.create_task(cleanup.run_cleanup_loop(stop_event))
    yield
    stop_event.set()
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    """构建 FastAPI 应用。"""
    app = FastAPI(
        title="File Explorer",
        description="沙箱化文件资源管理器服务",
        version="1.0.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(get_router())
    return app


app = create_app()


def main() -> None:
    """以 uvicorn 启动服务。"""
    config = get_config()
    config.port = 7860
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
