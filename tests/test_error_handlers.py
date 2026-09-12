"""错误处理器与请求追踪 ID 中间件的回归测试。

本模块覆盖以下场景：

- 路由未命中时返回统一 ``NOT_FOUND`` 错误响应；
- 业务异常抛出后返回统一 ``INVALID_PATH`` 错误响应；
- 请求参数校验失败时返回统一 ``VALIDATION_ERROR`` 错误响应；
- 未捕获异常被兜底为统一 ``INTERNAL_ERROR`` 错误响应；
- 请求追踪 ID 的回写与复用行为。
"""

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.errors import BusinessError, ErrorCode, register_exception_handlers
from app.middleware import RequestIdMiddleware


router_for_test = APIRouter()
"""测试专用路由，避免依赖真实业务路由。

变量名不使用 ``test_`` 前缀，避免被 pytest 误当作测试用例收集。
"""


@router_for_test.get("/raise-business-error")
def raise_business_error() -> None:
    """故意抛出业务异常，用于验证统一错误响应。

    Raises:
        BusinessError: 始终抛出 ``INVALID_PATH`` 业务异常。
    """
    raise BusinessError(ErrorCode.INVALID_PATH, "路径非法")


@router_for_test.get("/raise-uncaught-exception")
def raise_uncaught_exception() -> None:
    """故意抛出未捕获异常，用于验证兜底错误响应。

    Raises:
        RuntimeError: 始终抛出运行时异常。
    """
    raise RuntimeError("boom")


@router_for_test.get("/ok")
def ok_endpoint() -> dict[str, str]:
    """正常返回成功响应。

    Returns:
        固定字典，用于断言响应头中的请求追踪 ID。
    """
    return {"status": "ok"}


@router_for_test.get("/validate")
def validate_endpoint(page: int) -> dict[str, int]:
    """接收整型参数，用于触发 FastAPI 参数校验失败。

    Args:
        page: 页码，由 FastAPI 自动解析为整型。

    Returns:
        包含页码的字典。
    """
    return {"page": page}


def build_test_application() -> FastAPI:
    """构造测试专用的 FastAPI 应用。

    仅注册 :class:`RequestIdMiddleware`、全局异常处理器与测试路由，
    与生产入口 ``main.create_application`` 解耦。

    Returns:
        配置完成的 FastAPI 应用实例。
    """
    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(router_for_test)
    return application


application = build_test_application()
"""模块级测试应用实例。"""

client = TestClient(application, raise_server_exceptions=False)
"""模块级测试客户端，禁用异常直接抛出以验证兜底处理器。"""


def test_not_found_returns_unified_error_response() -> None:
    """未命中的路由应返回统一错误响应并携带请求追踪 ID。"""
    response = client.get("/definitely-not-exists")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "NOT_FOUND"
    assert isinstance(payload["message"], str)
    assert payload["requestId"] is not None
    assert response.headers.get("X-Request-ID") == payload["requestId"]


def test_business_error_returns_unified_error_response() -> None:
    """业务异常应被转换为统一错误响应。"""
    response = client.get("/raise-business-error")
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "INVALID_PATH"
    assert payload["message"] == "路径非法"
    assert payload["details"] is None


def test_validation_error_returns_unified_error_response() -> None:
    """参数校验失败应返回统一 ``VALIDATION_ERROR`` 响应。"""
    response = client.get("/validate", params={"page": "not-a-number"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["details"] is not None
    assert "errors" in payload["details"]


def test_uncaught_exception_returns_internal_error() -> None:
    """未捕获异常应被兜底为统一 ``INTERNAL_ERROR`` 响应。"""
    response = client.get("/raise-uncaught-exception")
    assert response.status_code == 500
    payload = response.json()
    assert payload["code"] == "INTERNAL_ERROR"
    assert payload["message"] == "服务端内部错误"


def test_request_id_from_client_is_echoed() -> None:
    """客户端传入的请求追踪 ID 应被原样回写。"""
    custom_request_id = "my-custom-request-id"
    response = client.get("/ok", headers={"X-Request-ID": custom_request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_request_id


def test_request_id_is_generated_when_absent() -> None:
    """客户端未传入请求追踪 ID 时应自动生成 32 位十六进制 ID。"""
    response = client.get("/ok")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    int(request_id, 16)  # 若非法十六进制会抛出 ValueError


def test_request_id_is_generated_for_error_response() -> None:
    """错误响应也应携带自动生成的请求追踪 ID。"""
    response = client.get("/raise-business-error")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 32
    payload = response.json()
    assert payload["requestId"] == request_id
