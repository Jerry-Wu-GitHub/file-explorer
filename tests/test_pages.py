"""页面路由的集成测试。

覆盖 ``/`` 与 ``/metadata`` 两个页面路由的成功与降级路径：
正常返回 HTML、带查询参数时返回同一页面、HTML 文件缺失时的
占位响应，以及页面路由不出现在 OpenAPI 文档中。
"""

from functools import partial
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.pages import router as pages_router


def create_config(static_directory: Path) -> Config:
    """返回以指定目录为静态资源目录的配置实例。

    Args:
        static_directory: 静态资源根目录。

    Returns:
        仅关注 ``static_directory`` 字段的配置对象。
    """
    return Config(static_directory=static_directory)


def build_client() -> TestClient:
    """构造仅包含页面路由的测试客户端。

    Returns:
        测试客户端。
    """
    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(pages_router)
    return TestClient(application, raise_server_exceptions=False)


@pytest.fixture
def static_directory(tmp_path: Path) -> Path:
    """创建包含示例 HTML 的静态目录。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        静态资源根目录。
    """
    directory = tmp_path / "static"
    html_directory = directory / "html"
    html_directory.mkdir(parents=True)
    (html_directory / "index.html").write_text(
        "<!DOCTYPE html><html><body>INDEX-PAGE</body></html>",
        encoding="utf-8",
    )
    (html_directory / "metadata.html").write_text(
        "<!DOCTYPE html><html><body>METADATA-PAGE</body></html>",
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def client(
    static_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """构造已替换配置的测试客户端。

    Args:
        static_directory: 静态资源根目录。
        monkeypatch: pytest 提供的 monkeypatch fixture。

    Returns:
        测试客户端。
    """
    fake_get_config = partial(create_config, static_directory)
    monkeypatch.setattr("app.routes.pages.get_config", fake_get_config)
    return build_client()


def test_index_page_returns_html(client: TestClient) -> None:
    """访问 ``/`` 应返回 200 与主页 HTML。"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "INDEX-PAGE" in response.text


def test_index_page_ignores_query_parameters(client: TestClient) -> None:
    """带 ``?path=`` 查询参数仍返回同一主页 HTML。"""
    response = client.get("/", params={"path": "/docs"})
    assert response.status_code == 200
    assert "INDEX-PAGE" in response.text


def test_metadata_page_returns_html(client: TestClient) -> None:
    """访问 ``/metadata`` 应返回属性页面 HTML。"""
    response = client.get("/metadata")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "METADATA-PAGE" in response.text


def test_metadata_page_accepts_path_query(client: TestClient) -> None:
    """带 ``?path=`` 查询参数仍返回属性页面 HTML。"""
    response = client.get("/metadata", params={"path": "/a.txt"})
    assert response.status_code == 200
    assert "METADATA-PAGE" in response.text


def test_index_page_returns_placeholder_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主页 HTML 缺失时应返回占位内容而非 500。"""
    directory = tmp_path / "static"
    html_directory = directory / "html"
    html_directory.mkdir(parents=True)
    (html_directory / "metadata.html").write_text("META", encoding="utf-8")

    fake_get_config = partial(create_config, directory)
    monkeypatch.setattr("app.routes.pages.get_config", fake_get_config)

    client = build_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "页面不存在" in response.text


def test_metadata_page_returns_placeholder_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """属性页面 HTML 缺失时应返回占位内容而非 500。"""
    directory = tmp_path / "static"
    html_directory = directory / "html"
    html_directory.mkdir(parents=True)
    (html_directory / "index.html").write_text("INDEX", encoding="utf-8")

    fake_get_config = partial(create_config, directory)
    monkeypatch.setattr("app.routes.pages.get_config", fake_get_config)

    client = build_client()
    response = client.get("/metadata")
    assert response.status_code == 200
    assert "页面不存在" in response.text


def test_page_routes_hidden_from_openapi(client: TestClient) -> None:
    """页面路由不应出现在 OpenAPI 文档中。"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json().get("paths", {})
    assert "/" not in paths
    assert "/metadata" not in paths
