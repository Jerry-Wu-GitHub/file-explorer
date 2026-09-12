"""压缩下载 API 集成测试。

覆盖 ``GET /api/v1/files/download-zip`` 的成功与失败路径，并验证
ZIP 内容、状态码与统一错误格式。
"""

import io
import zipfile
from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.dependencies.services import get_archive_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.files import router as files_router
from app.services.archive_service import ArchiveService
from app.services.path_service import PathService


FILES_PREFIX = "/api/v1/files"
"""测试用接口前缀。"""

ZIP_URL = f"{FILES_PREFIX}/download-zip"


def return_constant(value: ArchiveService) -> ArchiveService:
    """返回固定实例，配合 :func:`functools.partial` 用作依赖替换。"""
    return value


def build_client(sandbox: Path) -> TestClient:
    """构造使用指定沙箱根目录的测试客户端。"""
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    archive_service = ArchiveService(path_service)

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(files_router, prefix=FILES_PREFIX)
    application.dependency_overrides[get_archive_service] = partial(
        return_constant, archive_service
    )
    return TestClient(application, raise_server_exceptions=False)


def open_zip_response(response) -> zipfile.ZipFile:
    """将响应体解析为 :class:`zipfile.ZipFile`。

    Args:
        response: HTTP 响应对象。

    Returns:
        打开的内存 ZIP 对象。
    """
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_download_zip_single_file(tmp_path: Path) -> None:
    """单文件打包应返回 200 与合法 ZIP。"""
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    client = build_client(tmp_path)

    response = client.get(ZIP_URL, params={"paths": "/notes.txt"})
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/zip"
    assert "attachment" in response.headers["Content-Disposition"]

    with open_zip_response(response) as archive:
        assert archive.namelist() == ["notes.txt"]
        assert archive.read("notes.txt") == b"hello"


def test_download_zip_multiple_files(tmp_path: Path) -> None:
    """多个文件应全部包含。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    client = build_client(tmp_path)

    response = client.get(ZIP_URL, params={"paths": "/a.txt,/b.txt"})
    assert response.status_code == 200
    with open_zip_response(response) as archive:
        assert sorted(archive.namelist()) == ["a.txt", "b.txt"]


def test_download_zip_directory_recursive(tmp_path: Path) -> None:
    """目录应递归打包并保留目录结构。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "src" / "nested").mkdir()
    (tmp_path / "src" / "nested" / "b.txt").write_text("b", encoding="utf-8")
    client = build_client(tmp_path)

    response = client.get(ZIP_URL, params={"paths": "/src"})
    assert response.status_code == 200
    with open_zip_response(response) as archive:
        names = sorted(archive.namelist())
        assert names == ["src/a.txt", "src/nested/b.txt"]


def test_download_zip_mixed_inputs(tmp_path: Path) -> None:
    """文件与目录混合输入应正确打包。"""
    (tmp_path / "root.txt").write_text("r", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("a", encoding="utf-8")
    client = build_client(tmp_path)

    response = client.get(ZIP_URL, params={"paths": "/root.txt,/src"})
    assert response.status_code == 200
    with open_zip_response(response) as archive:
        assert sorted(archive.namelist()) == ["root.txt", "src/a.txt"]


def test_download_zip_ignores_blank_entries(tmp_path: Path) -> None:
    """路径列表中的空白项应被忽略。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    client = build_client(tmp_path)

    response = client.get(
        ZIP_URL, params={"paths": " /a.txt , , "}
    )
    assert response.status_code == 200
    with open_zip_response(response) as archive:
        assert archive.namelist() == ["a.txt"]


def test_download_zip_empty_paths_returns_422(tmp_path: Path) -> None:
    """空 ``paths`` 应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.get(ZIP_URL, params={"paths": ""})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_download_zip_rejects_nonexistent(tmp_path: Path) -> None:
    """不存在的路径应返回 ``NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.get(ZIP_URL, params={"paths": "/missing.txt"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_download_zip_rejects_parent_reference(tmp_path: Path) -> None:
    """含 ``..`` 的路径应返回 ``INVALID_PATH``。"""
    client = build_client(tmp_path)
    response = client.get(ZIP_URL, params={"paths": "/../etc/passwd"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PATH"


def test_download_zip_rejects_root(tmp_path: Path) -> None:
    """直接打包沙箱根目录应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.get(ZIP_URL, params={"paths": "/"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_download_zip_missing_paths_parameter(tmp_path: Path) -> None:
    """缺少 ``paths`` 参数应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.get(ZIP_URL)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
