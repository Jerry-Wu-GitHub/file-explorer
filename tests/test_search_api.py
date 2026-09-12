"""搜索 API 集成测试。

覆盖 ``GET /api/v1/files/search`` 的成功与失败路径、字段别名与
分页元数据。
"""

from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.dependencies.services import get_search_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.search import router as search_router
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.services.search_service import SearchService


FILES_PREFIX = "/api/v1/files"
"""测试用接口前缀。"""

SEARCH_URL = f"{FILES_PREFIX}/search"


def return_constant(value: SearchService) -> SearchService:
    """返回固定实例，配合 :func:`functools.partial` 用作依赖替换。"""
    return value


def build_client(sandbox: Path) -> TestClient:
    """构造使用指定沙箱根目录的测试客户端。"""
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    metadata_service = MetadataService(path_service)
    search_service = SearchService(path_service, metadata_service)

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(search_router, prefix=FILES_PREFIX)
    application.dependency_overrides[get_search_service] = partial(
        return_constant, search_service
    )
    return TestClient(application, raise_server_exceptions=False)


def prepare_tree(sandbox: Path) -> None:
    """准备一棵用于搜索的固定目录树（共 6 个条目）。

    结构：

    - /root.txt（5 字节，文件）
    - /docs/（目录）
    - /docs/report.pdf（10 字节，文件）
    - /docs/notes.md（3 字节，文件）
    - /images/（目录）
    - /images/photo.png（8 字节，文件）
    """
    (sandbox / "root.txt").write_bytes(b"hello")
    (sandbox / "docs").mkdir()
    (sandbox / "docs" / "report.pdf").write_bytes(b"%PDF-1.4aa")
    (sandbox / "docs" / "notes.md").write_bytes(b"abc")
    (sandbox / "images").mkdir()
    (sandbox / "images" / "photo.png").write_bytes(b"12345678")


def test_search_basic(tmp_path: Path) -> None:
    """无条件搜索应返回所有条目（共 6 个）。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(SEARCH_URL)
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 6
    assert payload["meta"]["page"] == 1
    assert payload["meta"]["size"] == 50


def test_search_by_keyword(tmp_path: Path) -> None:
    """关键词搜索应命中并返回正确条目。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(SEARCH_URL, params={"q": "REPORT"})
    payload = response.json()
    assert payload["meta"]["total"] == 1
    entry = payload["data"][0]
    assert entry["name"] == "report.pdf"
    assert entry["mimeType"] == "application/pdf"
    assert entry["isHidden"] is False


def test_search_filter_by_type(tmp_path: Path) -> None:
    """``type=file`` 时只返回文件（共 4 个）。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(SEARCH_URL, params={"type": "file"})
    payload = response.json()
    assert payload["meta"]["total"] == 4
    assert all(item["type"] == "file" for item in payload["data"])


def test_search_filter_by_size(tmp_path: Path) -> None:
    """``minSize`` / ``maxSize`` 应生效。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(
        SEARCH_URL,
        params={"type": "file", "minSize": 4, "maxSize": 10},
    )
    payload = response.json()
    names = sorted(item["name"] for item in payload["data"])
    assert names == ["photo.png", "report.pdf", "root.txt"]


def test_search_filter_by_time(tmp_path: Path) -> None:
    """``modifiedAfter`` 与 ``modifiedBefore`` 应生效。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(
        SEARCH_URL,
        params={
            "modifiedAfter": "2000-01-01T00:00:00Z",
            "modifiedBefore": "2100-01-01T00:00:00Z",
        },
    )
    payload = response.json()
    assert payload["meta"]["total"] == 6


def test_search_within_subdirectory(tmp_path: Path) -> None:
    """``path`` 限定搜索起始目录。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(SEARCH_URL, params={"path": "/docs"})
    payload = response.json()
    assert payload["meta"]["total"] == 2
    assert all(
        item["path"].startswith("/docs/") for item in payload["data"]
    )


def test_search_pagination(tmp_path: Path) -> None:
    """分页应返回正确切片与元数据。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(
        SEARCH_URL, params={"type": "file", "page": 2, "size": 1}
    )
    payload = response.json()
    assert payload["meta"]["total"] == 4
    assert payload["meta"]["page"] == 2
    assert payload["meta"]["size"] == 1
    assert len(payload["data"]) == 1


def test_search_empty_result(tmp_path: Path) -> None:
    """无匹配时返回空列表。"""
    prepare_tree(tmp_path)
    client = build_client(tmp_path)

    response = client.get(SEARCH_URL, params={"q": "no-match-xyz"})
    payload = response.json()
    assert payload["meta"]["total"] == 0
    assert payload["data"] == []


def test_search_rejects_inverted_size_range(tmp_path: Path) -> None:
    """``minSize > maxSize`` 应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.get(
        SEARCH_URL, params={"minSize": 100, "maxSize": 10}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_search_rejects_invalid_datetime(tmp_path: Path) -> None:
    """非法 ISO 8601 时间应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.get(
        SEARCH_URL, params={"modifiedAfter": "not-a-date"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_search_rejects_nonexistent_path(tmp_path: Path) -> None:
    """起始路径不存在时返回 ``NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.get(SEARCH_URL, params={"path": "/missing"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_search_rejects_parent_reference(tmp_path: Path) -> None:
    """路径含 ``..`` 时返回 ``INVALID_PATH``。"""
    client = build_client(tmp_path)
    response = client.get(SEARCH_URL, params={"path": "/../etc"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PATH"


def test_search_rejects_page_below_minimum(tmp_path: Path) -> None:
    """``page=0`` 应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.get(SEARCH_URL, params={"page": 0})
    assert response.status_code == 422


def test_search_rejects_size_above_maximum(tmp_path: Path) -> None:
    """``size`` 超上限应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.get(SEARCH_URL, params={"size": 1000})
    assert response.status_code == 422
