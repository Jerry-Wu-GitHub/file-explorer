"""WriteService 单元测试。

覆盖创建文件、创建文件夹、删除文件/目录/符号链接的成功与失败
路径。符号链接用例在 Windows 上默认跳过。
"""

import sys
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.services.write_service import WriteService


SYMLINK_SKIP_REASON = "Windows 创建符号链接需要管理员权限或开发者模式"
"""符号链接用例在 Windows 上跳过的原因说明。"""


def build_service(sandbox: Path) -> WriteService:
    """构造使用指定沙箱根目录的 :class:`WriteService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的写服务实例。
    """
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    return WriteService(path_service, MetadataService(path_service))


def test_create_file_success(tmp_path: Path) -> None:
    """创建文件应返回文件元数据。"""
    service = build_service(tmp_path)
    metadata = service.create_file("/notes.txt")
    assert metadata.name == "notes.txt"
    assert metadata.path == "/notes.txt"
    assert metadata.type == "file"
    assert metadata.size == 0
    assert (tmp_path / "notes.txt").is_file()


def test_create_file_in_nested_directory(tmp_path: Path) -> None:
    """在嵌套目录中创建文件应成功。"""
    (tmp_path / "docs").mkdir()
    service = build_service(tmp_path)
    metadata = service.create_file("/docs/notes.txt")
    assert metadata.path == "/docs/notes.txt"


def test_create_file_rejects_missing_parent(tmp_path: Path) -> None:
    """父目录不存在时抛出 ``PARENT_NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.create_file("/missing/notes.txt")
    assert exc_info.value.code == ErrorCode.PARENT_NOT_FOUND


def test_create_file_rejects_existing_file(tmp_path: Path) -> None:
    """目标已存在时抛出 ``FILE_EXISTS``。"""
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.create_file("/notes.txt")
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_create_file_rejects_parent_reference(tmp_path: Path) -> None:
    """路径含 ``..`` 时抛出 ``INVALID_PATH``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.create_file("/../evil.txt")
    assert exc_info.value.code == ErrorCode.INVALID_PATH


def test_create_folder_success(tmp_path: Path) -> None:
    """创建文件夹应返回目录元数据。"""
    service = build_service(tmp_path)
    metadata = service.create_folder("/documents")
    assert metadata.name == "documents"
    assert metadata.type == "directory"
    assert metadata.mime_type is None
    assert (tmp_path / "documents").is_dir()


def test_create_folder_rejects_missing_parent(tmp_path: Path) -> None:
    """父目录不存在时抛出 ``PARENT_NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.create_folder("/missing/sub")
    assert exc_info.value.code == ErrorCode.PARENT_NOT_FOUND


def test_create_folder_rejects_existing(tmp_path: Path) -> None:
    """目标已存在时抛出 ``FILE_EXISTS``。"""
    (tmp_path / "documents").mkdir()
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.create_folder("/documents")
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_delete_file_success(tmp_path: Path) -> None:
    """删除文件应成功。"""
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    service.delete_entry("/notes.txt")
    assert not (tmp_path / "notes.txt").exists()


def test_delete_empty_directory_success(tmp_path: Path) -> None:
    """删除空目录应成功。"""
    (tmp_path / "empty").mkdir()
    service = build_service(tmp_path)
    service.delete_entry("/empty")
    assert not (tmp_path / "empty").exists()


def test_delete_non_empty_directory_rejects_without_recursive(
    tmp_path: Path,
) -> None:
    """目录非空且 ``recursive=False`` 时抛出 ``DIRECTORY_NOT_EMPTY``。"""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.txt").write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.delete_entry("/sub", recursive=False)
    assert exc_info.value.code == ErrorCode.DIRECTORY_NOT_EMPTY


def test_delete_non_empty_directory_with_recursive(tmp_path: Path) -> None:
    """``recursive=True`` 时应递归删除整个目录。"""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.txt").write_text("", encoding="utf-8")
    (tmp_path / "sub" / "nested").mkdir()
    service = build_service(tmp_path)
    service.delete_entry("/sub", recursive=True)
    assert not (tmp_path / "sub").exists()


def test_delete_nonexistent_raises_not_found(tmp_path: Path) -> None:
    """删除不存在的路径抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.delete_entry("/missing")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_delete_rejects_parent_reference(tmp_path: Path) -> None:
    """路径含 ``..`` 时抛出 ``INVALID_PATH``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.delete_entry("/../evil")
    assert exc_info.value.code == ErrorCode.INVALID_PATH


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_delete_symlink_without_follow(tmp_path: Path) -> None:
    """``follow_link=False`` 时只删除符号链接本身。"""
    target = tmp_path / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    service = build_service(tmp_path)

    service.delete_entry("/link.txt", follow_link=False)
    assert not link.exists()
    assert target.exists()


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_delete_symlink_with_follow(tmp_path: Path) -> None:
    """``follow_link=True`` 时删除符号链接指向的目标。"""
    target = tmp_path / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    service = build_service(tmp_path)

    service.delete_entry("/link.txt", follow_link=True)
    assert link.is_symlink()
    assert not target.exists()
