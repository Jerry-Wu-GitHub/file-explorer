"""SmallFileUploadService 单元测试。

覆盖成功上传、覆盖语义、文件名清洗、目录校验、大小限制以及
错误路径。
"""

import io
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.services.small_file_upload_service import (
    SmallFileUploadService,
    sanitize_upload_filename,
)


DEFAULT_MAX_UPLOAD_SIZE = 20 * 1024 * 1024 * 1024
"""测试默认使用的上传大小上限。"""


def build_service(
    sandbox: Path,
    max_upload_size: int = DEFAULT_MAX_UPLOAD_SIZE,
) -> SmallFileUploadService:
    """构造使用指定沙箱根目录的小文件上传服务。

    Args:
        sandbox: 用作沙箱根目录的临时路径。
        max_upload_size: 上传大小上限，默认 20 GiB。

    Returns:
        配置好的上传服务实例。
    """
    config = Config(sandbox_root=sandbox, max_upload_size=max_upload_size)
    path_service = PathService(config)
    return SmallFileUploadService(
        path_service, MetadataService(path_service), config
    )


def test_sanitize_upload_filename_basic() -> None:
    """普通文件名原样返回。"""
    assert sanitize_upload_filename("notes.txt") == "notes.txt"
    assert sanitize_upload_filename("  notes.txt  ") == "notes.txt"


def test_sanitize_upload_filename_strips_paths() -> None:
    """含路径分隔符的名称只保留最后一段。"""
    assert sanitize_upload_filename("a/b/c.txt") == "c.txt"
    assert sanitize_upload_filename("a\\b\\c.txt") == "c.txt"
    assert sanitize_upload_filename("../evil.txt") == "evil.txt"


def test_sanitize_upload_filename_rejects_empty() -> None:
    """空文件名抛出 ``VALIDATION_ERROR``。"""
    with pytest.raises(BusinessError) as exc_info:
        sanitize_upload_filename(None)
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    with pytest.raises(BusinessError) as exc_info:
        sanitize_upload_filename("   ")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_sanitize_upload_filename_rejects_dot_names() -> None:
    """``.``、``..`` 与含空字节的名称被拒绝。"""
    with pytest.raises(BusinessError):
        sanitize_upload_filename(".")
    with pytest.raises(BusinessError):
        sanitize_upload_filename("..")
    with pytest.raises(BusinessError):
        sanitize_upload_filename("a\0b.txt")


def test_upload_file_success(tmp_path: Path) -> None:
    """上传到已存在目录应生成目标文件与元数据。"""
    service = build_service(tmp_path)
    content = io.BytesIO(b"hello world")
    metadata = service.upload_file("/", "notes.txt", content)

    assert metadata.name == "notes.txt"
    assert metadata.path == "/notes.txt"
    assert metadata.type == "file"
    assert metadata.mime_type == "text/plain"
    assert metadata.size == 11
    assert (tmp_path / "notes.txt").read_bytes() == b"hello world"


def test_upload_file_to_subdirectory(tmp_path: Path) -> None:
    """上传到子目录应正确生成虚拟路径。"""
    (tmp_path / "docs").mkdir()
    service = build_service(tmp_path)
    metadata = service.upload_file(
        "/docs", "report.txt", io.BytesIO(b"data")
    )
    assert metadata.path == "/docs/report.txt"


def test_upload_file_empty_content(tmp_path: Path) -> None:
    """空文件上传应成功且大小为 0。"""
    service = build_service(tmp_path)
    metadata = service.upload_file("/", "empty.txt", io.BytesIO(b""))
    assert metadata.size == 0
    assert (tmp_path / "empty.txt").exists()


def test_upload_file_uses_sanitized_filename(tmp_path: Path) -> None:
    """含路径的文件名应只保留最后一段。"""
    service = build_service(tmp_path)
    metadata = service.upload_file(
        "/", "some/path/notes.txt", io.BytesIO(b"x")
    )
    assert metadata.name == "notes.txt"


def test_upload_file_rejects_existing_without_overwrite(
    tmp_path: Path,
) -> None:
    """目标存在且未允许覆盖时抛出 ``FILE_EXISTS``。"""
    (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.upload_file("/", "notes.txt", io.BytesIO(b"new"))
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_upload_file_overwrites_when_allowed(tmp_path: Path) -> None:
    """``overwrite=True`` 时应替换原文件。"""
    (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
    service = build_service(tmp_path)
    service.upload_file("/", "notes.txt", io.BytesIO(b"new"), overwrite=True)
    assert (tmp_path / "notes.txt").read_bytes() == b"new"


def test_upload_file_rejects_existing_directory(tmp_path: Path) -> None:
    """目标为目录时即使允许覆盖也拒绝。"""
    (tmp_path / "docs").mkdir()
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.upload_file("/", "docs", io.BytesIO(b"x"), overwrite=True)
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_upload_file_rejects_missing_directory(tmp_path: Path) -> None:
    """目标目录不存在时抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.upload_file("/missing", "notes.txt", io.BytesIO(b"x"))
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_upload_file_rejects_file_as_directory(tmp_path: Path) -> None:
    """``path`` 指向文件时抛出 ``NOT_FOUND``。"""
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.upload_file("/notes.txt", "other.txt", io.BytesIO(b"y"))
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_upload_file_rejects_parent_reference(tmp_path: Path) -> None:
    """``path`` 含 ``..`` 时抛出 ``INVALID_PATH``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.upload_file("/../etc", "passwd", io.BytesIO(b"x"))
    assert exc_info.value.code == ErrorCode.INVALID_PATH


def test_upload_file_rejects_oversized_content(tmp_path: Path) -> None:
    """内容超过配置上限时抛出 ``PAYLOAD_TOO_LARGE``。"""
    service = build_service(tmp_path, max_upload_size=1024)
    oversized = io.BytesIO(b"x" * 2048)
    with pytest.raises(BusinessError) as exc_info:
        service.upload_file("/", "big.bin", oversized)
    assert exc_info.value.code == ErrorCode.PAYLOAD_TOO_LARGE


def test_upload_file_no_temp_files_left_on_failure(tmp_path: Path) -> None:
    """上传失败后临时文件应被清理。"""
    service = build_service(tmp_path, max_upload_size=10)
    with pytest.raises(BusinessError):
        service.upload_file("/", "big.bin", io.BytesIO(b"x" * 100))

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_upload_file_metadata_reflects_content(tmp_path: Path) -> None:
    """返回的元数据应与实际写入内容一致。"""
    service = build_service(tmp_path)
    metadata = service.upload_file(
        "/", "hello.txt", io.BytesIO(b"hello world")
    )
    stat_result = (tmp_path / "hello.txt").stat()
    assert metadata.size == stat_result.st_size
