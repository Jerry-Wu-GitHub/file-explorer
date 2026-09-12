"""HTTP 服务器相关的常量定义。

本模块集中定义 HTTP 服务运行所需的基础常量，
包括监听地址、端口、API 前缀、静态资源前缀、CORS 等。

其中部分常量可通过同名环境变量覆盖，具体解析逻辑请参考
``app.config`` 模块。
"""

HOST: str = "127.0.0.1"
"""默认的 HTTP 服务监听地址。"""

PORT: int = 8000
"""默认的 HTTP 服务监听端口。"""

API_PREFIX: str = "/api/v1"
"""业务 API 路由的公共前缀。"""

STATIC_PREFIX: str = "/static"
"""静态资源路由的公共前缀。"""

REQUEST_ID_HEADER: str = "X-Request-ID"
"""请求追踪 ID 使用的 HTTP 头部名称。"""

CORS_ALLOWED_ORIGINS: str = "*"
"""CORS 允许的来源，多个来源以英文逗号分隔，``*`` 表示全部允许。"""

SERVE_STATIC_FILES: bool = True
"""是否启用静态文件服务。"""

LOG_LEVEL: str = "info"
"""默认的日志级别，可选 ``debug``、``info``、``warning``、``error``。"""

__all__ = [
    "HOST",
    "PORT",
    "API_PREFIX",
    "STATIC_PREFIX",
    "REQUEST_ID_HEADER",
    "CORS_ALLOWED_ORIGINS",
    "SERVE_STATIC_FILES",
    "LOG_LEVEL",
]
