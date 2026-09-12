"""MetadataService 单元测试。

覆盖普通文件、目录、隐藏文件、不存在的路径，以及符号链接在
跟随与不跟随模式下的元数据组装。符号链接用例在 Windows 上默认
跳过，因为创建符号链接需要管理员权限或开启开发者模式。
"""

import sys
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService


SYMLINK_SKIP_REASON = "Windows 创建符号链接需要管理员权限或开发者模式"
"""符号链接用例在 Windows 上跳过的原因说明。"""


def build_service(sandbox: Path) -> MetadataService:
    """构造使用指定沙箱根目录的 :class:`MetadataService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的元数据服务实例。
    """
    config = Config(sandbox_root=sandbox)
    return MetadataService(PathService(config))


def test_build_metadata_for_file(tmp_path: Path) -> None:
    """普通文件应返回完整的元数据。"""
    file_path = tmp_path / "hello.txt"
    file_path.write_text("hello world", encoding="utf-8")
    service = build_service(tmp_path)

    metadata = service.build_metadata(file_path)
    assert metadata.name == "hello.txt"
    assert metadata.path == "/hello.txt"
    assert metadata.type == "file"
    assert metadata.mime_type == "text/plain"
    assert metadata.size == 11
    assert metadata.is_hidden is False
    assert len(metadata.permissions) == 9


def test_build_metadata_for_directory(tmp_path: Path) -> None:
    """目录的 MIME 为 ``None``、大小为 0。"""
    dir_path = tmp_path / "documents"
    dir_path.mkdir()
    service = build_service(tmp_path)

    metadata = service.build_metadata(dir_path)
    assert metadata.name == "documents"
    assert metadata.path == "/documents"
    assert metadata.type == "directory"
    assert metadata.mime_type is None
    assert metadata.size == 0
    assert metadata.is_hidden is False


def test_build_metadata_for_hidden_file(tmp_path: Path) -> None:
    """以点开头的文件应被标记为隐藏。"""
    hidden = tmp_path / ".env"
    hidden.write_text("SECRET=1", encoding="utf-8")
    service = build_service(tmp_path)

    metadata = service.build_metadata(hidden)
    assert metadata.is_hidden is True


def test_build_metadata_for_nested_file(tmp_path: Path) -> None:
    """嵌套路径应生成正确的虚拟路径与 MIME。"""
    sub = tmp_path / "docs" / "reports"
    sub.mkdir(parents=True)
    file_path = sub / "annual.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    service = build_service(tmp_path)

    metadata = service.build_metadata(file_path)
    assert metadata.path == "/docs/reports/annual.pdf"
    assert metadata.mime_type == "application/pdf"


def test_build_metadata_for_nonexistent_path(tmp_path: Path) -> None:
    """不存在的路径应抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.build_metadata(tmp_path / "nonexistent.txt")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_build_metadata_for_symlink_with_follow(tmp_path: Path) -> None:
    """``follow_link=True`` 时符号链接以目标类型呈现。"""
    target = tmp_path / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    service = build_service(tmp_path)

    metadata = service.build_metadata(link, follow_link=True)
    assert metadata.type == "file"
    assert metadata.name == "link.txt"
    assert metadata.path == "/link.txt"
    assert metadata.mime_type == "text/plain"


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_build_metadata_for_symlink_without_follow(tmp_path: Path) -> None:
    """``follow_link=False`` 时符号链接以 ``link`` 类型呈现。"""
    target = tmp_path / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    service = build_service(tmp_path)

    metadata = service.build_metadata(link, follow_link=False)
    assert metadata.type == "link"
    assert metadata.mime_type is None
    assert metadata.size == 0


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_build_metadata_for_dangling_symlink_with_follow(
    tmp_path: Path,
) -> None:
    """悬空符号链接在 ``follow_link=True`` 时应抛出 ``NOT_FOUND``。"""
    link = tmp_path / "dangling"
    link.symlink_to(tmp_path / "nonexistent")
    service = build_service(tmp_path)

    with pytest.raises(BusinessError) as exc_info:
        service.build_metadata(link, follow_link=True)
    assert exc_info.value.code == ErrorCode.NOT_FOUND


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_build_metadata_for_dangling_symlink_without_follow(
    tmp_path: Path,
) -> None:
    """悬空符号链接在 ``follow_link=False`` 时仍应以 ``link`` 返回。"""
    link = tmp_path / "dangling"
    link.symlink_to(tmp_path / "nonexistent")
    service = build_service(tmp_path)

    metadata = service.build_metadata(link, follow_link=False)
    assert metadata.type == "link"
