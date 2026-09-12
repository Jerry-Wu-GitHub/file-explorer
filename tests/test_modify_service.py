"""ModifyService 单元测试。

覆盖元数据修改（重命名、移动、时间、权限、隐藏属性）与复制的
成功与失败路径。符号链接相关用例在 Windows 上默认跳过。
"""

import os
import sys
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.schemas.write import UpdateMetadataRequest
from app.services.metadata_service import MetadataService
from app.services.modify_service import ModifyService
from app.services.path_service import PathService


SYMLINK_SKIP_REASON = "Windows 创建符号链接需要管理员权限或开发者模式"
"""符号链接用例在 Windows 上跳过的原因说明。"""


def build_service(sandbox: Path) -> ModifyService:
    """构造使用指定沙箱根目录的 :class:`ModifyService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的修改服务实例。
    """
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    return ModifyService(path_service, MetadataService(path_service))


def test_update_metadata_rename(tmp_path: Path) -> None:
    """只提供 ``name`` 时应重命名。"""
    (tmp_path / "old.txt").write_text("hello", encoding="utf-8")
    service = build_service(tmp_path)
    metadata = service.update_metadata(
        "/old.txt", UpdateMetadataRequest(name="new.txt")
    )
    assert metadata.name == "new.txt"
    assert metadata.path == "/new.txt"
    assert not (tmp_path / "old.txt").exists()
    assert (tmp_path / "new.txt").is_file()


def test_update_metadata_move(tmp_path: Path) -> None:
    """只提供 ``path`` 时应移动 + 重命名。"""
    (tmp_path / "old.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    service = build_service(tmp_path)
    metadata = service.update_metadata(
        "/old.txt", UpdateMetadataRequest(path="/docs/new.txt")
    )
    assert metadata.path == "/docs/new.txt"
    assert (tmp_path / "docs" / "new.txt").is_file()
    assert not (tmp_path / "old.txt").exists()


def test_update_metadata_path_takes_precedence_over_name(
    tmp_path: Path,
) -> None:
    """同时提供 ``name`` 与 ``path`` 时忽略 ``name``。"""
    (tmp_path / "old.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    service = build_service(tmp_path)
    metadata = service.update_metadata(
        "/old.txt",
        UpdateMetadataRequest(name="ignored.txt", path="/docs/actual.txt"),
    )
    assert metadata.name == "actual.txt"
    assert metadata.path == "/docs/actual.txt"
    assert not (tmp_path / "ignored.txt").exists()


def test_update_metadata_rename_rejects_existing_target(
    tmp_path: Path,
) -> None:
    """重命名到已存在的目标时抛出 ``FILE_EXISTS``。"""
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.update_metadata("/a.txt", UpdateMetadataRequest(name="b.txt"))
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_update_metadata_modified_time(tmp_path: Path) -> None:
    """提供 ``modifiedAt`` 时应修改修改时间。"""
    file_path = tmp_path / "file.txt"
    file_path.write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    new_mtime = 1_600_000_000.0
    metadata = service.update_metadata(
        "/file.txt", UpdateMetadataRequest(modified_at=new_mtime)
    )
    assert metadata.modified_at == pytest.approx(new_mtime, abs=1)


def test_update_metadata_accessed_time(tmp_path: Path) -> None:
    """提供 ``accessedAt`` 时应修改访问时间。"""
    file_path = tmp_path / "file.txt"
    file_path.write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    new_atime = 1_600_000_000.0
    service.update_metadata(
        "/file.txt", UpdateMetadataRequest(accessed_at=new_atime)
    )
    stat_result = os.stat(file_path)
    assert stat_result.st_atime == pytest.approx(new_atime, abs=1)


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows 的 chmod 不支持完整权限位"
)
def test_update_metadata_permissions(tmp_path: Path) -> None:
    """提供 ``permissions`` 时应修改权限。"""
    file_path = tmp_path / "file.txt"
    file_path.write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    metadata = service.update_metadata(
        "/file.txt", UpdateMetadataRequest(permissions="rwxr-xr-x")
    )
    assert metadata.permissions == "rwxr-xr-x"
    assert (os.stat(file_path).st_mode & 0o777) == 0o755


def test_update_metadata_toggle_hidden_on(tmp_path: Path) -> None:
    """``isHidden=True`` 时添加前导点。"""
    (tmp_path / "visible.txt").write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    metadata = service.update_metadata(
        "/visible.txt", UpdateMetadataRequest(is_hidden=True)
    )
    assert metadata.name == ".visible.txt"
    assert metadata.is_hidden is True
    assert (tmp_path / ".visible.txt").is_file()


def test_update_metadata_toggle_hidden_off(tmp_path: Path) -> None:
    """``isHidden=False`` 时去掉前导点。"""
    (tmp_path / ".hidden.txt").write_text("", encoding="utf-8")
    service = build_service(tmp_path)
    metadata = service.update_metadata(
        "/.hidden.txt", UpdateMetadataRequest(is_hidden=False)
    )
    assert metadata.name == "hidden.txt"
    assert metadata.is_hidden is False


def test_update_metadata_rejects_nonexistent(tmp_path: Path) -> None:
    """目标不存在时抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.update_metadata(
            "/missing.txt", UpdateMetadataRequest(name="new.txt")
        )
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_update_metadata_empty_request_is_noop(tmp_path: Path) -> None:
    """空请求应返回原始元数据，不修改任何内容。"""
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello", encoding="utf-8")
    service = build_service(tmp_path)
    metadata = service.update_metadata(
        "/file.txt", UpdateMetadataRequest()
    )
    assert metadata.name == "file.txt"
    assert metadata.size == 5


def test_copy_file_success(tmp_path: Path) -> None:
    """复制文件应生成副本。"""
    (tmp_path / "source.txt").write_text("hello", encoding="utf-8")
    service = build_service(tmp_path)
    metadata = service.copy_entry("/source.txt", "/copy.txt")
    assert metadata.name == "copy.txt"
    assert (tmp_path / "copy.txt").read_text(encoding="utf-8") == "hello"
    assert (tmp_path / "source.txt").exists()


def test_copy_directory_success(tmp_path: Path) -> None:
    """递归复制文件夹应生成完整副本。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "src" / "nested").mkdir()
    (tmp_path / "src" / "nested" / "b.txt").write_text("b", encoding="utf-8")
    service = build_service(tmp_path)

    metadata = service.copy_entry("/src", "/dst")
    assert metadata.type == "directory"
    assert (tmp_path / "dst" / "a.txt").read_text(encoding="utf-8") == "a"
    assert (tmp_path / "dst" / "nested" / "b.txt").exists()


def test_copy_rejects_existing_target_without_overwrite(
    tmp_path: Path,
) -> None:
    """目标已存在且未允许覆盖时抛出 ``FILE_EXISTS``。"""
    (tmp_path / "source.txt").write_text("a", encoding="utf-8")
    (tmp_path / "target.txt").write_text("b", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.copy_entry("/source.txt", "/target.txt", overwrite=False)
    assert exc_info.value.code == ErrorCode.FILE_EXISTS


def test_copy_overwrites_existing_target(tmp_path: Path) -> None:
    """``overwrite=True`` 时覆盖目标文件。"""
    (tmp_path / "source.txt").write_text("new", encoding="utf-8")
    (tmp_path / "target.txt").write_text("old", encoding="utf-8")
    service = build_service(tmp_path)
    service.copy_entry("/source.txt", "/target.txt", overwrite=True)
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "new"


def test_copy_rejects_missing_source(tmp_path: Path) -> None:
    """源不存在时抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.copy_entry("/missing.txt", "/target.txt")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_copy_rejects_missing_parent(tmp_path: Path) -> None:
    """目标父目录不存在时抛出 ``PARENT_NOT_FOUND``。"""
    (tmp_path / "source.txt").write_text("a", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.copy_entry("/source.txt", "/missing/target.txt")
    assert exc_info.value.code == ErrorCode.PARENT_NOT_FOUND
