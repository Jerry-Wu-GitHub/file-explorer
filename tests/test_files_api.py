"""文件系统只读 API 集成测试。

覆盖 ``GET /api/v1/files`` 与 ``GET /api/v1/files/metadata`` 的
成功与失败路径，包括分页、排序、过滤、路径越界、参数校验等
场景，同时验证响应字段使用小驼峰命名。
"""

from functools import partial
from pathlib import Path
from typing import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.dependencies.services import get_file_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.files import router as files_router
from app.services.file_service import FileService
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService


FILES_PREFIX = "/api/v1/files"
"""测试用 API 前缀，与生产路由前缀保持一致。"""


def return_constant(value: FileService) -> FileService:
    """返回固定的文件服务实例。

    该函数与 :func:`functools.partial` 配合，构造一个无参可调用对象，
    用于替换 FastAPI 依赖，避免在测试中定义闭包。

    Args:
        value: 要返回的文件服务。

    Returns:
        入参 ``value`` 本身。
    """
    return value


def build_test_client(sandbox: Path) -> TestClient:
    """构造使用指定沙箱根目录的测试客户端。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        可直接发起请求的 :class:`TestClient` 实例。
    """
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    metadata_service = MetadataService(path_service)
    file_service = FileService(path_service, metadata_service)

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(files_router, prefix=FILES_PREFIX)
    application.dependency_overrides[get_file_service] = partial(
        return_constant, file_service
    )
    return TestClient(application, raise_server_exceptions=False)


def prepare_sample_directory(sandbox: Path) -> None:
    """在沙箱内准备一组固定的测试条目。

    Args:
        sandbox: 沙箱根目录。
    """
    (sandbox / "documents").mkdir()
    (sandbox / "documents" / "report.pdf").write_bytes(b"%PDF-1.4")
    (sandbox / "readme.md").write_text("# readme", encoding="utf-8")
    (sandbox / "notes.txt").write_text("hello", encoding="utf-8")


def test_list_directory_returns_entries_and_meta(tmp_path: Path) -> None:
    """列出根目录应返回条目与分页元数据。"""
    prepare_sample_directory(tmp_path)
    client = build_test_client(tmp_path)

    response = client.get(FILES_PREFIX, params={"path": "/"})
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert "meta" in payload
    assert payload["meta"]["total"] == 3
    assert payload["meta"]["page"] == 1
    assert payload["meta"]["size"] == 50
    names = sorted(item["name"] for item in payload["data"])
    assert names == ["documents", "notes.txt", "readme.md"]


def test_list_directory_entry_uses_camel_case(tmp_path: Path) -> None:
    """条目字段应使用小驼峰命名。"""
    prepare_sample_directory(tmp_path)
    client = build_test_client(tmp_path)

    response = client.get(FILES_PREFIX, params={"path": "/"})
    payload = response.json()
    entry = next(
        item for item in payload["data"] if item["name"] == "notes.txt"
    )
    assert entry["mimeType"] == "text/plain"
    assert entry["createdAt"] > 0
    assert entry["modifiedAt"] > 0
    assert entry["accessedAt"] > 0
    assert entry["isHidden"] is False
    assert entry["permissions"]
    assert "mime_type" not in entry
    assert "created_at" not in entry


def test_list_directory_nested_directory(tmp_path: Path) -> None:
    """列出嵌套目录应返回正确的虚拟路径。"""
    prepare_sample_directory(tmp_path)
    client = build_test_client(tmp_path)

    response = client.get(FILES_PREFIX, params={"path": "/documents"})
    payload = response.json()
    assert payload["meta"]["total"] == 1
    entry = payload["data"][0]
    assert entry["name"] == "report.pdf"
    assert entry["path"] == "/documents/report.pdf"


def test_list_directory_pagination(tmp_path: Path) -> None:
    """分页应返回正确切片。"""
    for index in range(10):
        (tmp_path / f"file_{index:02d}.txt").write_text(
            str(index), encoding="utf-8"
        )
    client = build_test_client(tmp_path)

    response = client.get(
        FILES_PREFIX,
        params={"path": "/", "page": 2, "size": 3, "sort": "name,asc"},
    )
    payload = response.json()
    assert payload["meta"]["total"] == 10
    assert payload["meta"]["page"] == 2
    assert payload["meta"]["size"] == 3
    assert [item["name"] for item in payload["data"]] == [
        "file_03.txt",
        "file_04.txt",
        "file_05.txt",
    ]


def test_list_directory_sort_desc(tmp_path: Path) -> None:
    """按名称降序应返回逆序结果。"""
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    (tmp_path / "c.txt").write_text("", encoding="utf-8")
    client = build_test_client(tmp_path)

    response = client.get(
        FILES_PREFIX, params={"path": "/", "sort": "name,desc"}
    )
    payload = response.json()
    assert [item["name"] for item in payload["data"]] == [
        "c.txt",
        "b.txt",
        "a.txt",
    ]


def test_list_directory_filter_type(tmp_path: Path) -> None:
    """``type=directory`` 时只返回目录。"""
    prepare_sample_directory(tmp_path)
    client = build_test_client(tmp_path)

    response = client.get(
        FILES_PREFIX, params={"path": "/", "type": "directory"}
    )
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert payload["data"][0]["name"] == "documents"
    assert payload["data"][0]["type"] == "directory"


def test_list_directory_nonexistent_returns_404(tmp_path: Path) -> None:
    """列出不存在的目录应返回 ``NOT_FOUND``。"""
    client = build_test_client(tmp_path)
    response = client.get(FILES_PREFIX, params={"path": "/nonexistent"})
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "NOT_FOUND"
    assert payload["requestId"] is not None


def test_list_directory_on_file_returns_404(tmp_path: Path) -> None:
    """对文件调用列表接口应返回 ``NOT_FOUND``。"""
    prepare_sample_directory(tmp_path)
    client = build_test_client(tmp_path)
    response = client.get(FILES_PREFIX, params={"path": "/notes.txt"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_list_directory_rejects_parent_reference(tmp_path: Path) -> None:
    """包含 ``..`` 的路径应返回 ``INVALID_PATH``。"""
    client = build_test_client(tmp_path)
    response = client.get(FILES_PREFIX, params={"path": "/../etc/passwd"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PATH"


def test_list_directory_rejects_invalid_sort(tmp_path: Path) -> None:
    """非法排序表达式应返回 ``VALIDATION_ERROR``。"""
    client = build_test_client(tmp_path)
    response = client.get(FILES_PREFIX, params={"path": "/", "sort": "bad"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_directory_rejects_page_below_minimum(tmp_path: Path) -> None:
    """``page=0`` 应返回 ``VALIDATION_ERROR``。"""
    client = build_test_client(tmp_path)
    response = client.get(FILES_PREFIX, params={"path": "/", "page": 0})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_list_directory_rejects_size_above_maximum(tmp_path: Path) -> None:
    """``size`` 超过上限应返回 ``VALIDATION_ERROR``。"""
    client = build_test_client(tmp_path)
    response = client.get(FILES_PREFIX, params={"path": "/", "size": 1000})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_get_metadata_file(tmp_path: Path) -> None:
    """获取文件元数据应成功。"""
    prepare_sample_directory(tmp_path)
    client = build_test_client(tmp_path)

    response = client.get(
        f"{FILES_PREFIX}/metadata", params={"path": "/notes.txt"}
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "notes.txt"
    assert payload["path"] == "/notes.txt"
    assert payload["type"] == "file"
    assert payload["mimeType"] == "text/plain"
    assert payload["size"] == 5
    assert payload["isHidden"] is False


def test_get_metadata_directory(tmp_path: Path) -> None:
    """获取目录元数据应成功。"""
    prepare_sample_directory(tmp_path)
    client = build_test_client(tmp_path)

    response = client.get(
        f"{FILES_PREFIX}/metadata", params={"path": "/documents"}
    )
    payload = response.json()["data"]
    assert payload["type"] == "directory"
    assert payload["mimeType"] is None
    assert payload["size"] == 0


def test_get_metadata_default_path_is_root(tmp_path: Path) -> None:
    """未提供 ``path`` 时默认查询沙箱根目录。"""
    client = build_test_client(tmp_path)
    response = client.get(f"{FILES_PREFIX}/metadata")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["path"] == "/"
    assert payload["type"] == "directory"


def test_get_metadata_nonexistent_returns_404(tmp_path: Path) -> None:
    """不存在的路径应返回 ``NOT_FOUND``。"""
    client = build_test_client(tmp_path)
    response = client.get(
        f"{FILES_PREFIX}/metadata", params={"path": "/missing.txt"}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_get_metadata_rejects_parent_reference(tmp_path: Path) -> None:
    """包含 ``..`` 的路径应返回 ``INVALID_PATH``。"""
    client = build_test_client(tmp_path)
    response = client.get(
        f"{FILES_PREFIX}/metadata", params={"path": "/../etc/passwd"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PATH"
