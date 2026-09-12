"""ContentService 单元测试。

覆盖完整下载、Range 请求以及各类失败路径。
"""

from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.services.content_service import ContentService, build_etag
from app.services.path_service import PathService
from app.utils.http_range import RangeRequest, RangeStatus


def build_service(sandbox: Path) -> ContentService:
    """构造使用指定沙箱根目录的 :class:`ContentService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的内容服务实例。
    """
    config = Config(sandbox_root=sandbox)
    return ContentService(PathService(config))


def test_prepare_content_without_range(tmp_path: Path) -> None:
    """未提供 Range 时状态为 ``ABSENT``。"""
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello world", encoding="utf-8")
    service = build_service(tmp_path)

    descriptor = service.prepare_content("/notes.txt", True, None)
    assert descriptor.filename == "notes.txt"
    assert descriptor.file_size == 11
    assert descriptor.mime_type == "text/plain"
    assert descriptor.range_result.status == RangeStatus.ABSENT
    assert descriptor.etag.startswith('"') and descriptor.etag.endswith('"')


def test_prepare_content_with_valid_range(tmp_path: Path) -> None:
    """有效的 Range 应解析为 VALID。"""
    file_path = tmp_path / "notes.txt"
    file_path.write_text("0123456789", encoding="utf-8")
    service = build_service(tmp_path)

    descriptor = service.prepare_content("/notes.txt", True, "bytes=2-5")
    assert descriptor.range_result.status == RangeStatus.VALID
    assert descriptor.range_result.request == RangeRequest(start=2, end=5)


def test_prepare_content_with_invalid_range(tmp_path: Path) -> None:
    """无效 Range 应解析为 INVALID。"""
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello", encoding="utf-8")
    service = build_service(tmp_path)

    descriptor = service.prepare_content("/notes.txt", True, "bytes=999-")
    assert descriptor.range_result.status == RangeStatus.INVALID


def test_prepare_content_directory_raises_not_found(tmp_path: Path) -> None:
    """目录不能作为内容下载目标，应返回 ``NOT_FOUND``。"""
    (tmp_path / "documents").mkdir()
    service = build_service(tmp_path)

    with pytest.raises(BusinessError) as exc_info:
        service.prepare_content("/documents", True, None)
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_prepare_content_nonexistent_raises_not_found(
    tmp_path: Path,
) -> None:
    """不存在的路径应返回 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.prepare_content("/missing.txt", True, None)
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_prepare_content_rejects_parent_reference(tmp_path: Path) -> None:
    """含 ``..`` 的路径应返回 ``INVALID_PATH``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.prepare_content("/../etc/passwd", True, None)
    assert exc_info.value.code == ErrorCode.INVALID_PATH


def test_build_etag_is_stable_and_quoted() -> None:
    """ETag 应为带引号的确定性字符串。"""
    first = build_etag(123456789, 100)
    second = build_etag(123456789, 100)
    assert first == second
    assert first.startswith('"') and first.endswith('"')


def test_build_etag_changes_with_mtime_and_size() -> None:
    """修改时间或大小变化时 ETag 应变化。"""
    base = build_etag(100, 200)
    assert build_etag(101, 200) != base
    assert build_etag(100, 201) != base
