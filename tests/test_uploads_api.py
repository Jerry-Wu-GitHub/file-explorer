"""分片上传 HTTP 接口集成测试。

覆盖完整的生命周期：初始化 → 上传分片 → 查询 → 完成 / 取消，
以及各阶段的错误响应与统一格式。
"""

from functools import partial
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.constants import MAX_CHUNK_SIZE, MIN_CHUNK_SIZE
from app.dependencies.services import get_chunked_upload_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.repositories.upload_session_repository import (
    UploadSessionRepository,
)
from app.routes.uploads import router as uploads_router
from app.services.chunked_upload_service import ChunkedUploadService
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.storage.upload_chunk_storage import LocalUploadChunkStorage
from app.storage.upload_lock_manager import UploadLockManager


FILES_PREFIX = "/api/v1/files"
"""测试用接口前缀。"""

UPLOADS_URL = f"{FILES_PREFIX}/uploads"
"""初始化分片上传的接口地址。"""


def return_constant(value: ChunkedUploadService) -> ChunkedUploadService:
    """返回固定实例，配合 :func:`functools.partial` 用作依赖替换。"""
    return value


def build_client(
    tmp_path: Path,
    default_chunk_size: int = 1024 * 1024,
    min_chunk_size: int = MIN_CHUNK_SIZE,
    max_chunk_size: int = MAX_CHUNK_SIZE,
    max_upload_size: int = 20 * 1024 * 1024 * 1024,
) -> TestClient:
    """构造使用指定沙箱根目录的测试客户端。

    Args:
        tmp_path: pytest 提供的临时目录。
        default_chunk_size: 默认分片大小。
        min_chunk_size: 最小分片大小。
        max_chunk_size: 最大分片大小。
        max_upload_size: 单个文件大小上限。

    Returns:
        配置好的 :class:`TestClient`。
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    upload_temp_root = tmp_path / "upload_temp"
    upload_temp_root.mkdir(exist_ok=True)
    database_path = upload_temp_root / "uploads.sqlite3"

    config = Config(
        sandbox_root=sandbox,
        upload_temp_root=upload_temp_root,
        upload_database_path=database_path,
        default_chunk_size=default_chunk_size,
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
        max_upload_size=max_upload_size,
    )
    path_service = PathService(config)
    metadata_service = MetadataService(path_service)
    repository = UploadSessionRepository(database_path)
    storage = LocalUploadChunkStorage(upload_temp_root)
    lock_manager = UploadLockManager(upload_temp_root / "locks")
    service = ChunkedUploadService(
        path_service,
        metadata_service,
        repository,
        storage,
        lock_manager,
        config,
    )

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(uploads_router, prefix=FILES_PREFIX)
    application.dependency_overrides[get_chunked_upload_service] = partial(
        return_constant, service
    )
    return TestClient(application, raise_server_exceptions=False)


# ---------- 初始化 ----------


def test_initialize_upload_success(tmp_path: Path) -> None:
    """初始化应返回 201 与会话信息。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOADS_URL,
        json={"path": "/large.bin", "size": 1500},
    )
    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["uploadId"]
    assert payload["path"] == "/large.bin"
    assert payload["size"] == 1500
    assert payload["chunkSize"] == 1024 * 1024
    assert payload["totalChunks"] == 1
    assert payload["uploadedChunks"] == []
    assert payload["missingChunks"] == [0]
    assert payload["status"] == "created"


def test_initialize_upload_rejects_trailing_slash(tmp_path: Path) -> None:
    """``path`` 以 ``/`` 结尾应返回 ``VALIDATION_ERROR``。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOADS_URL, json={"path": "/docs/", "size": 100}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_initialize_upload_rejects_missing_parent(tmp_path: Path) -> None:
    """父目录不存在应返回 ``PARENT_NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOADS_URL, json={"path": "/missing/a.bin", "size": 100}
    )
    assert response.status_code == 404
    assert response.json()["code"] == "PARENT_NOT_FOUND"


def test_initialize_upload_rejects_existing_without_overwrite(
    tmp_path: Path,
) -> None:
    """目标存在且未允许覆盖应返回 ``FILE_EXISTS``。"""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    (sandbox / "a.bin").write_bytes(b"x")
    client = build_client(tmp_path)
    response = client.post(
        UPLOADS_URL, json={"path": "/a.bin", "size": 100}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "FILE_EXISTS"


def test_initialize_upload_accepts_camel_case_body(tmp_path: Path) -> None:
    """请求体应支持小驼峰字段。"""
    client = build_client(tmp_path)
    response = client.post(
        UPLOADS_URL,
        json={
            "path": "/large.bin",
            "size": 1000,
            "chunkSize": 1024 * 512,
            "overwrite": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["data"]["chunkSize"] == 1024 * 512


# ---------- 状态查询 ----------


def test_get_upload_status_after_init(tmp_path: Path) -> None:
    """初始化后查询状态应返回 ``created``。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    response = client.get(f"{UPLOADS_URL}/{created['uploadId']}")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "created"
    assert payload["missingChunks"] == [0]


def test_get_upload_status_nonexistent(tmp_path: Path) -> None:
    """不存在的 ID 应返回 ``UPLOAD_NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.get(f"{UPLOADS_URL}/not-a-real-id")
    assert response.status_code == 404
    assert response.json()["code"] == "UPLOAD_NOT_FOUND"


# ---------- 上传分片 ----------


def test_upload_chunk_success(tmp_path: Path) -> None:
    """上传单个分片应返回 200 与分片统计。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]

    response = client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["uploadId"] == created["uploadId"]
    assert payload["chunkNumber"] == 0
    assert payload["receivedSize"] == 1000
    assert payload["uploadedChunks"] == 1
    assert payload["totalChunks"] == 1
    assert payload["uploadedBytes"] == 1000
    assert payload["status"] == "uploading"


def test_upload_chunk_with_md5_header(tmp_path: Path) -> None:
    """携带正确的 ``Content-MD5`` 应通过校验。"""
    import hashlib

    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    payload = b"a" * 1000
    md5_hex = hashlib.md5(payload).hexdigest()

    response = client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=payload,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-MD5": md5_hex,
        },
    )
    assert response.status_code == 200


def test_upload_chunk_with_bad_md5_header(tmp_path: Path) -> None:
    """MD5 不匹配应返回 ``CHECKSUM_MISMATCH``。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]

    response = client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 1000,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-MD5": "0" * 32,
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHECKSUM_MISMATCH"


def test_upload_chunk_rejects_out_of_range(tmp_path: Path) -> None:
    """编号越界应返回 ``CHUNK_OUT_OF_RANGE``。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]

    response = client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/5",
        content=b"a" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 416
    assert response.json()["code"] == "CHUNK_OUT_OF_RANGE"


def test_upload_chunk_rejects_wrong_size(tmp_path: Path) -> None:
    """分片大小不符应返回 ``INVALID_CHUNK_SIZE``。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]

    response = client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 500,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_CHUNK_SIZE"


def test_upload_chunk_rejects_canceled_session(tmp_path: Path) -> None:
    """取消后的会话上传分片应返回 ``UPLOAD_CANCELED`` 或 ``UPLOAD_NOT_FOUND``。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    client.delete(f"{UPLOADS_URL}/{created['uploadId']}")

    response = client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code in (404, 409)
    assert response.json()["code"] in ("UPLOAD_NOT_FOUND", "UPLOAD_CANCELED")


# ---------- 完成上传 ----------


def test_complete_upload_success(tmp_path: Path) -> None:
    """上传全部分片后完成应返回 201 与文件元数据。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )

    response = client.post(
        f"{UPLOADS_URL}/{created['uploadId']}/complete",
        json={},
    )
    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["name"] == "large.bin"
    assert payload["path"] == "/large.bin"
    assert payload["type"] == "file"
    assert payload["size"] == 1000
    assert (tmp_path / "sandbox" / "large.bin").read_bytes() == b"a" * 1000


def test_complete_upload_incomplete_returns_409(tmp_path: Path) -> None:
    """分片缺失应返回 ``UPLOAD_INCOMPLETE`` 与缺失列表。"""
    client = build_client(tmp_path, default_chunk_size=512, min_chunk_size=128)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1500}
    ).json()["data"]

    response = client.post(
        f"{UPLOADS_URL}/{created['uploadId']}/complete",
        json={},
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "UPLOAD_INCOMPLETE"
    assert payload["details"]["missingChunks"] == [0, 1, 2]


def test_complete_upload_repeat_is_idempotent(tmp_path: Path) -> None:
    """重复调用完成应返回 200 与现有元数据。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )
    first = client.post(
        f"{UPLOADS_URL}/{created['uploadId']}/complete", json={}
    )
    second = client.post(
        f"{UPLOADS_URL}/{created['uploadId']}/complete", json={}
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["path"] == second.json()["data"]["path"]


def test_complete_upload_checksum_mismatch(tmp_path: Path) -> None:
    """整体 checksum 校验失败应返回 ``CHECKSUM_MISMATCH``。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )

    response = client.post(
        f"{UPLOADS_URL}/{created['uploadId']}/complete",
        json={"checksum": {"algorithm": "sha256", "value": "0" * 64}},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "CHECKSUM_MISMATCH"


# ---------- 取消上传 ----------


def test_cancel_upload_success(tmp_path: Path) -> None:
    """取消上传应返回 204。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    response = client.delete(f"{UPLOADS_URL}/{created['uploadId']}")
    assert response.status_code == 204
    assert response.content == b""

    status_response = client.get(f"{UPLOADS_URL}/{created['uploadId']}")
    assert status_response.status_code == 404


def test_cancel_upload_is_idempotent(tmp_path: Path) -> None:
    """重复取消应返回 204。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    first = client.delete(f"{UPLOADS_URL}/{created['uploadId']}")
    second = client.delete(f"{UPLOADS_URL}/{created['uploadId']}")
    assert first.status_code == 204
    assert second.status_code == 204


def test_cancel_upload_nonexistent_is_noop(tmp_path: Path) -> None:
    """取消不存在的会话应返回 204。"""
    client = build_client(tmp_path)
    response = client.delete(f"{UPLOADS_URL}/not-a-real-id")
    assert response.status_code == 204


def test_cancel_upload_rejects_completed(tmp_path: Path) -> None:
    """已完成的会话取消应返回 ``UPLOAD_ALREADY_COMPLETED``。"""
    client = build_client(tmp_path)
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1000}
    ).json()["data"]
    client.put(
        f"{UPLOADS_URL}/{created['uploadId']}/chunks/0",
        content=b"a" * 1000,
        headers={"Content-Type": "application/octet-stream"},
    )
    client.post(
        f"{UPLOADS_URL}/{created['uploadId']}/complete", json={}
    )

    response = client.delete(f"{UPLOADS_URL}/{created['uploadId']}")
    assert response.status_code == 409
    assert response.json()["code"] == "UPLOAD_ALREADY_COMPLETED"


# ---------- 完整生命周期 ----------


def test_full_lifecycle_multi_chunk(tmp_path: Path) -> None:
    """完整生命周期：初始化 → 上传 → 查询 → 完成。"""
    client = build_client(
        tmp_path,
        default_chunk_size=512,
        min_chunk_size=128,
        max_chunk_size=1024 * 1024,
    )
    created = client.post(
        UPLOADS_URL, json={"path": "/large.bin", "size": 1500}
    ).json()["data"]
    assert created["totalChunks"] == 3

    for chunk_number, payload in enumerate([b"a" * 512, b"b" * 512, b"c" * 476]):
        response = client.put(
            f"{UPLOADS_URL}/{created['uploadId']}/chunks/{chunk_number}",
            content=payload,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert response.status_code == 200

    status = client.get(
        f"{UPLOADS_URL}/{created['uploadId']}"
    ).json()["data"]
    assert status["uploadedChunks"] == [0, 1, 2]
    assert status["missingChunks"] == []

    completed = client.post(
        f"{UPLOADS_URL}/{created['uploadId']}/complete", json={}
    )
    assert completed.status_code == 201
    assert (tmp_path / "sandbox" / "large.bin").read_bytes() == (
        b"a" * 512 + b"b" * 512 + b"c" * 476
    )
