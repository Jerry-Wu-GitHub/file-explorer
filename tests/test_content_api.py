"""内容下载 API 集成测试。

覆盖 200 完整下载、206 部分下载、416 无效 Range、404 不存在、
400 非法路径以及响应头字段。
"""

from functools import partial
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.dependencies.services import get_content_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.files import router as files_router
from app.services.content_service import ContentService
from app.services.path_service import PathService


FILES_PREFIX = "/api/v1/files"
"""测试用文件接口前缀。"""

CONTENT_URL = f"{FILES_PREFIX}/content"


def return_constant(value: ContentService) -> ContentService:
    """返回固定实例，配合 :func:`functools.partial` 用作依赖替换。"""
    return value


def build_client(sandbox: Path) -> TestClient:
    """构造使用指定沙箱根目录的测试客户端。"""
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    content_service = ContentService(path_service)

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(files_router, prefix=FILES_PREFIX)
    application.dependency_overrides[get_content_service] = partial(
        return_constant, content_service
    )
    return TestClient(application, raise_server_exceptions=False)


def prepare_file(sandbox: Path, name: str, content: bytes) -> Path:
    """在沙箱内准备一个测试文件。

    Args:
        sandbox: 沙箱根目录。
        name: 文件名。
        content: 文件内容。

    Returns:
        文件真实路径。
    """
    file_path = sandbox / name
    file_path.write_bytes(content)
    return file_path


def test_download_full_file(tmp_path: Path) -> None:
    """无 Range 头时应返回完整文件与 200。"""
    prepare_file(tmp_path, "notes.txt", b"hello world")
    client = build_client(tmp_path)

    response = client.get(CONTENT_URL, params={"path": "/notes.txt"})
    assert response.status_code == 200
    assert response.content == b"hello world"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert response.headers["Content-Length"] == "11"
    assert response.headers["Content-Type"].startswith("text/plain")
    assert "ETag" in response.headers
    assert "Last-Modified" in response.headers
    assert "attachment" in response.headers["Content-Disposition"]


def test_download_closed_range(tmp_path: Path) -> None:
    """闭区间 Range 应返回 206 与正确切片。"""
    prepare_file(tmp_path, "data.bin", b"0123456789")
    client = build_client(tmp_path)

    response = client.get(
        CONTENT_URL,
        params={"path": "/data.bin"},
        headers={"Range": "bytes=2-5"},
    )
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["Content-Range"] == "bytes 2-5/10"
    assert response.headers["Content-Length"] == "4"


def test_download_open_ended_range(tmp_path: Path) -> None:
    """``bytes=start-`` 应返回从 start 到文件末尾。"""
    prepare_file(tmp_path, "data.bin", b"0123456789")
    client = build_client(tmp_path)

    response = client.get(
        CONTENT_URL,
        params={"path": "/data.bin"},
        headers={"Range": "bytes=5-"},
    )
    assert response.status_code == 206
    assert response.content == b"56789"
    assert response.headers["Content-Range"] == "bytes 5-9/10"


def test_download_suffix_range(tmp_path: Path) -> None:
    """``bytes=-N`` 应返回末尾 N 字节。"""
    prepare_file(tmp_path, "data.bin", b"0123456789")
    client = build_client(tmp_path)

    response = client.get(
        CONTENT_URL,
        params={"path": "/data.bin"},
        headers={"Range": "bytes=-3"},
    )
    assert response.status_code == 206
    assert response.content == b"789"
    assert response.headers["Content-Range"] == "bytes 7-9/10"


def test_download_invalid_range_returns_416(tmp_path: Path) -> None:
    """起始位置超过文件大小时返回 416。"""
    prepare_file(tmp_path, "data.bin", b"0123456789")
    client = build_client(tmp_path)

    response = client.get(
        CONTENT_URL,
        params={"path": "/data.bin"},
        headers={"Range": "bytes=100-200"},
    )
    assert response.status_code == 416
    assert response.headers["Content-Range"] == "bytes */10"


def test_download_reversed_range_returns_416(tmp_path: Path) -> None:
    """起始大于结束时返回 416。"""
    prepare_file(tmp_path, "data.bin", b"0123456789")
    client = build_client(tmp_path)

    response = client.get(
        CONTENT_URL,
        params={"path": "/data.bin"},
        headers={"Range": "bytes=8-2"},
    )
    assert response.status_code == 416


def test_download_nonexistent_returns_404(tmp_path: Path) -> None:
    """不存在的文件返回 ``NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.get(CONTENT_URL, params={"path": "/missing.txt"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_download_directory_returns_404(tmp_path: Path) -> None:
    """目录返回 ``NOT_FOUND``。"""
    (tmp_path / "documents").mkdir()
    client = build_client(tmp_path)
    response = client.get(CONTENT_URL, params={"path": "/documents"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_download_rejects_parent_reference(tmp_path: Path) -> None:
    """含 ``..`` 的路径返回 ``INVALID_PATH``。"""
    client = build_client(tmp_path)
    response = client.get(CONTENT_URL, params={"path": "/../etc/passwd"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PATH"


def test_download_unicode_filename_content_disposition(
    tmp_path: Path,
) -> None:
    """含非 ASCII 字符的文件名应使用 RFC 5987 编码。"""
    prepare_file(tmp_path, "报告.txt", "hello".encode("utf-8"))
    client = build_client(tmp_path)

    response = client.get(CONTENT_URL, params={"path": "/报告.txt"})
    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    assert "filename*=UTF-8''" in disposition


def test_download_empty_file(tmp_path: Path) -> None:
    """空文件返回 200 且 Content-Length 为 0。"""
    prepare_file(tmp_path, "empty.txt", b"")
    client = build_client(tmp_path)

    response = client.get(CONTENT_URL, params={"path": "/empty.txt"})
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["Content-Length"] == "0"


def test_download_empty_file_with_range_returns_416(
    tmp_path: Path,
) -> None:
    """空文件加任意 Range 应返回 416。"""
    prepare_file(tmp_path, "empty.txt", b"")
    client = build_client(tmp_path)

    response = client.get(
        CONTENT_URL,
        params={"path": "/empty.txt"},
        headers={"Range": "bytes=0-10"},
    )
    assert response.status_code == 416
    assert response.headers["Content-Range"] == "bytes */0"
