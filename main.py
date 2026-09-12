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

from fastapi import FastAPI
import uvicorn

from app import lifespan, get_router, register_exception_handlers
from app.config import get_config

app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.include_router(get_router())


if __name__ == '__main__':
    config = get_config()
    uvicorn.run(app, host=config.host, port=config.port)
