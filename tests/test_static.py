"""静态资源路由的集成测试。

覆盖 ``/static`` 前缀下文件的正常访问、MIME 类型、404、目录
列表不暴露、路径遍历防护，以及静态目录不存在时不挂载的行为。
"""

from functools import partial
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.static import mount_static_files


def create_config(static_directory: Path) -> Config:
    """返回以指定目录为静态资源目录的配置实例。

    Args:
        static_directory: 静态资源根目录。

    Returns:
        仅关注 ``static_directory`` 字段的配置对象。
    """
    return Config(static_directory=static_directory)


def build_client() -> TestClient:
    """构造仅包含静态资源挂载的测试客户端。

    注意：本函数依赖调用方先通过 ``monkeypatch`` 替换
    ``app.routes.static.get_config``，否则会挂载真实目录。

    Returns:
        测试客户端。
    """
    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    mount_static_files(application)
    return TestClient(application, raise_server_exceptions=False)


@pytest.fixture
def static_directory(tmp_path: Path) -> Path:
    """创建包含示例资源文件的静态目录。

    Args:
        tmp_path: pytest 提供的临时目录。

    Returns:
        静态资源根目录。
    """
    directory = tmp_path / "static"
    css_directory = directory / "css"
    js_directory = directory / "js"
    css_directory.mkdir(parents=True)
    js_directory.mkdir(parents=True)
    (css_directory / "theme.css").write_text(
        ":root { --accent: #00e676; }",
        encoding="utf-8",
    )
    (js_directory / "main.js").write_text(
        "export const ready = true;",
        encoding="utf-8",
    )
    (directory / "readme.txt").write_text("hello", encoding="utf-8")
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
    monkeypatch.setattr("app.routes.static.get_config", fake_get_config)
    return build_client()


def test_static_returns_css(client: TestClient) -> None:
    """访问 CSS 文件应返回 200 与 text/css。"""
    response = client.get("/static/css/theme.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--accent" in response.text


def test_static_returns_javascript(client: TestClient) -> None:
    """访问 JS 文件应返回 JavaScript MIME。"""
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "ready" in response.text


def test_static_returns_plain_text(client: TestClient) -> None:
    """访问文本文件应返回 text/plain。"""
    response = client.get("/static/readme.txt")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert response.text == "hello"


def test_static_missing_file_returns_404(client: TestClient) -> None:
    """不存在的静态文件应返回 404。"""
    response = client.get("/static/css/missing.css")
    assert response.status_code == 404


def test_static_directory_listing_not_exposed(client: TestClient) -> None:
    """静态目录不应暴露目录列表。"""
    response = client.get("/static/css/")
    assert response.status_code == 404


def test_static_unknown_directory_returns_404(client: TestClient) -> None:
    """不存在的子目录应返回 404。"""
    response = client.get("/static/unknown/file.txt")
    assert response.status_code == 404


def test_static_path_traversal_blocked(client: TestClient) -> None:
    """路径遍历尝试应被阻止。"""
    response = client.get("/static/..%2Freadme.txt")
    assert response.status_code in (400, 403, 404)


def test_static_prefix_confined_to_mounted_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """静态前缀不会暴露挂载目录以外的文件。"""
    outside = tmp_path / "outside.txt"
    outside.write_text("top-secret", encoding="utf-8")

    directory = tmp_path / "static"
    directory.mkdir()

    fake_get_config = partial(create_config, directory)
    monkeypatch.setattr("app.routes.static.get_config", fake_get_config)

    client = build_client()
    response = client.get("/static/..%2Foutside.txt")
    assert response.status_code in (400, 403, 404)
    assert "top-secret" not in response.text


def test_static_not_mounted_when_directory_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """静态目录不存在时不挂载，访问返回 404。"""
    missing_directory = tmp_path / "does_not_exist"
    fake_get_config = partial(create_config, missing_directory)
    monkeypatch.setattr("app.routes.static.get_config", fake_get_config)

    client = build_client()
    response = client.get("/static/css/theme.css")
    assert response.status_code == 404
