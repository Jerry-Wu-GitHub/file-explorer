"""上传相关 Schema 的单元测试。

覆盖字段默认值、别名、约束与错误校验。
"""

import pytest
from pydantic import ValidationError

from app.constants import (
    DEFAULT_CHUNK_SIZE,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
)
from app.schemas.upload import (
    ChecksumSchema,
    InitializeUploadRequest,
    UploadSessionResponse,
)


def test_checksum_schema_accepts_sha256() -> None:
    """合法的 sha256 校验信息应被接受。"""
    checksum = ChecksumSchema(algorithm="sha256", value="deadbeef")
    assert checksum.algorithm == "sha256"
    assert checksum.value == "deadbeef"


def test_checksum_schema_accepts_md5() -> None:
    """合法的 md5 校验信息应被接受。"""
    checksum = ChecksumSchema(algorithm="md5", value="abc")
    assert checksum.algorithm == "md5"


def test_checksum_schema_rejects_unknown_algorithm() -> None:
    """未定义的算法应被拒绝。"""
    with pytest.raises(ValidationError):
        ChecksumSchema(algorithm="sha1", value="abc")


def test_checksum_schema_rejects_empty_value() -> None:
    """空的校验值应被拒绝。"""
    with pytest.raises(ValidationError):
        ChecksumSchema(algorithm="sha256", value="")


def test_initialize_request_minimal() -> None:
    """仅提供必填字段时使用默认值。"""
    request = InitializeUploadRequest(path="/large.zip", size=1000)
    assert request.path == "/large.zip"
    assert request.size == 1000
    assert request.chunk_size is None
    assert request.overwrite is False
    assert request.checksum is None


def test_initialize_request_accepts_camel_case_alias() -> None:
    """应支持使用小驼峰别名构造。"""
    request = InitializeUploadRequest(
        path="/large.zip",
        size=1000,
        chunkSize=DEFAULT_CHUNK_SIZE,
        overwrite=True,
        checksum={"algorithm": "sha256", "value": "abc"},
    )
    assert request.chunk_size == DEFAULT_CHUNK_SIZE
    assert request.overwrite is True
    assert request.checksum is not None
    assert request.checksum.algorithm == "sha256"


def test_initialize_request_rejects_negative_size() -> None:
    """负的 size 应被拒绝。"""
    with pytest.raises(ValidationError):
        InitializeUploadRequest(path="/a", size=-1)


def test_initialize_request_rejects_empty_path() -> None:
    """空的 path 应被拒绝。"""
    with pytest.raises(ValidationError):
        InitializeUploadRequest(path="", size=0)


def test_initialize_request_rejects_chunk_size_below_minimum() -> None:
    """小于最小分片大小的值应被拒绝。"""
    with pytest.raises(ValidationError):
        InitializeUploadRequest(
            path="/a", size=1000, chunk_size=MIN_CHUNK_SIZE - 1
        )


def test_initialize_request_rejects_chunk_size_above_maximum() -> None:
    """大于最大分片大小的值应被拒绝。"""
    with pytest.raises(ValidationError):
        InitializeUploadRequest(
            path="/a", size=1000, chunk_size=MAX_CHUNK_SIZE + 1
        )


def test_initialize_request_rejects_extra_field() -> None:
    """未定义字段应被拒绝。"""
    with pytest.raises(ValidationError):
        InitializeUploadRequest(path="/a", size=0, unknown="x")


def test_upload_session_response_serialization_uses_camel_case() -> None:
    """响应序列化应使用小驼峰。"""
    response = UploadSessionResponse(
        upload_id="u1",
        path="/a.bin",
        size=100,
        chunk_size=10,
        total_chunks=10,
        uploaded_chunks=[0, 1],
        missing_chunks=[2, 3],
        uploaded_bytes=20,
        status="uploading",
        created_at=1000.0,
        updated_at=1000.0,
        expires_at=2000.0,
    )
    payload = response.model_dump(by_alias=True)
    assert payload["uploadId"] == "u1"
    assert payload["chunkSize"] == 10
    assert payload["totalChunks"] == 10
    assert payload["uploadedChunks"] == [0, 1]
    assert payload["missingChunks"] == [2, 3]
    assert payload["uploadedBytes"] == 20
    assert payload["createdAt"] == 1000.0
    assert payload["expiresAt"] == 2000.0


def test_upload_session_response_rejects_unknown_status() -> None:
    """未定义的状态应被拒绝。"""
    with pytest.raises(ValidationError):
        UploadSessionResponse(
            upload_id="u1",
            path="/a.bin",
            size=100,
            chunk_size=10,
            total_chunks=10,
            uploaded_chunks=[],
            missing_chunks=[],
            uploaded_bytes=0,
            status="unknown",
            created_at=1000.0,
            updated_at=1000.0,
            expires_at=2000.0,
        )
