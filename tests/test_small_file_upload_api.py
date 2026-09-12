"""小文件上传 API 集成测试。

覆盖 ``POST /api/v1/files/upload`` 的成功与失败路径、字段别名、
错误码与状态码。
"""

from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.dependencies.services import get_small_file_upload_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.files import router as files_router
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.services.small_file_upload_service import SmallFileUploadService


FILES_PREFIX = "/api/v1/files"
"""测试用接口前缀。"""

UPLOAD_URL = f"{FILES_PREFIX}/upload"

DEFAULT_MAX_UPLOAD_SIZE = 20 * 1024 * 1024 * 1024
"""测试默认使用的上传大小上限。"""


def return_constant(value: SmallFileUploadService) -> SmallFileUploadService:
    """返回固定实例，配合 :func:`functools.partial` 用作依赖替换。"""
    return value


def build_client(
    sandbox: Path,
    max_upload_size: int = DEFAULT_MAX_UPLOAD_SIZE,
) -> TestClient:
    """构造使用指定沙箱根目录的测试客户端。"""
    config = Config(sandbox_root=sandbox, max_upload_size=max_upload_size)
    path_service = PathService(config)
    metadata_service = MetadataService(path_service)
    upload_service = SmallFileUploadService(
        path_service, metadata_service, config
    )

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(files_router, prefix=FILES_PREFIX)
    application.dependency_overrides[get_small_file_upload_service] = partial(
        return_constant, upload_service
    )
    return TestClient(application, raise_server_exceptions=False)


def test_upload_file_success(tmp_path: Path) -> None:
    """上传成功应返回 201 与文件元数据。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["name"] == "notes.txt"
    assert payload["path"] == "/notes.txt"
    assert payload["type"] == "file"
    assert payload["size"] == 11
    assert payload["mimeType"] == "text/plain"
    assert payload["isHidden"] is False
    assert (tmp_path / "notes.txt").read_bytes() == b"hello world"


def test_upload_file_to_subdirectory(tmp_path: Path) -> None:
    """上传到子目录应正确构造虚拟路径。"""
    (tmp_path / "docs").mkdir()
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/docs"},
        files={"file": ("report.txt", b"data", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["data"]["path"] == "/docs/report.txt"


def test_upload_file_empty(tmp_path: Path) -> None:
    """空文件上传应成功。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["data"]["size"] == 0


def test_upload_file_rejects_existing_without_overwrite(
    tmp_path: Path,
) -> None:
    """目标存在且未允许覆盖时返回 ``FILE_EXISTS``。"""
    (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("notes.txt", b"new", "text/plain")},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "FILE_EXISTS"


def test_upload_file_overwrites_when_allowed(tmp_path: Path) -> None:
    """``overwrite=true`` 时应覆盖原文件。"""
    (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("notes.txt", b"new", "text/plain")},
        data={"overwrite": "true"},
    )
    assert response.status_code == 201
    assert (tmp_path / "notes.txt").read_bytes() == b"new"


def test_upload_file_rejects_existing_directory(tmp_path: Path) -> None:
    """目标为目录时返回 ``FILE_EXISTS``。"""
    (tmp_path / "docs").mkdir()
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("docs", b"x", "text/plain")},
        data={"overwrite": "true"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "FILE_EXISTS"


def test_upload_file_rejects_missing_directory(tmp_path: Path) -> None:
    """目标目录不存在时返回 ``NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/missing"},
        files={"file": ("notes.txt", b"x", "text/plain")},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_upload_file_rejects_parent_reference(tmp_path: Path) -> None:
    """``path`` 含 ``..`` 时返回 ``INVALID_PATH``。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/../etc"},
        files={"file": ("passwd", b"x", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PATH"


def test_upload_file_rejects_oversized(tmp_path: Path) -> None:
    """内容超过上限时返回 ``PAYLOAD_TOO_LARGE``。"""
    client = build_client(tmp_path, max_upload_size=1024)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("big.bin", b"x" * 2048, "application/octet-stream")},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_upload_file_requires_file_field(tmp_path: Path) -> None:
    """缺少 ``file`` 字段时返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.post(UPLOAD_URL, params={"path": "/"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_upload_file_requires_path_parameter(tmp_path: Path) -> None:
    """缺少 ``path`` 参数时返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        files={"file": ("notes.txt", b"x", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_upload_file_sanitizes_client_filename(tmp_path: Path) -> None:
    """客户端提供的路径式文件名应只保留最后一段。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("a/b/c/notes.txt", b"x", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "notes.txt"


def test_upload_file_uses_default_overwrite_false(tmp_path: Path) -> None:
    """未提供 ``overwrite`` 时默认为 false，同名文件被拒绝。"""
    (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(
        UPLOAD_URL,
        params={"path": "/"},
        files={"file": ("notes.txt", b"new", "text/plain")},
    )
    assert response.status_code == 409
