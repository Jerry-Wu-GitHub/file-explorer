"""FileService 单元测试。

覆盖目录列表的过滤、排序、分页、隐藏项目控制，以及元数据查询
的成功与失败路径。符号链接相关用例在 Windows 上默认跳过。
"""

import sys
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.services.file_service import FileService
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService


SYMLINK_SKIP_REASON = "Windows 创建符号链接需要管理员权限或开发者模式"
"""符号链接用例在 Windows 上跳过的原因说明。"""


def build_service(sandbox: Path) -> FileService:
    """构造使用指定沙箱根目录的 :class:`FileService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的文件服务实例。
    """
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    metadata_service = MetadataService(path_service)
    return FileService(path_service, metadata_service)


def test_list_directory_returns_all_entries(tmp_path: Path) -> None:
    """列出目录应返回所有条目及总数。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("bb", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    service = build_service(tmp_path)

    entries, total = service.list_directory("/", show_hidden=True)
    assert total == 3
    assert sorted(entry.name for entry in entries) == [
        "a.txt",
        "b.txt",
        "subdir",
    ]


def test_list_directory_empty_directory(tmp_path: Path) -> None:
    """空目录应返回空列表与 0 总数。"""
    service = build_service(tmp_path)
    entries, total = service.list_directory("/")
    assert entries == []
    assert total == 0


def test_list_directory_pagination(tmp_path: Path) -> None:
    """分页应返回正确的切片。"""
    for index in range(10):
        (tmp_path / f"file_{index:02d}.txt").write_text(
            str(index), encoding="utf-8"
        )
    service = build_service(tmp_path)

    entries, total = service.list_directory(
        "/", page=2, size=3, sort="name,asc"
    )
    assert total == 10
    assert [entry.name for entry in entries] == [
        "file_03.txt",
        "file_04.txt",
        "file_05.txt",
    ]


def test_list_directory_sort_by_name_desc(tmp_path: Path) -> None:
    """按名称降序排序应返回逆序结果。"""
    (tmp_path / "a.txt").write_text("", encoding="utf-8")
    (tmp_path / "b.txt").write_text("", encoding="utf-8")
    (tmp_path / "c.txt").write_text("", encoding="utf-8")
    service = build_service(tmp_path)

    entries, _ = service.list_directory(
        "/", sort="name,desc", show_hidden=True
    )
    assert [entry.name for entry in entries] == ["c.txt", "b.txt", "a.txt"]


def test_list_directory_sort_by_size_asc(tmp_path: Path) -> None:
    """按大小升序排序。"""
    (tmp_path / "small.txt").write_text("a", encoding="utf-8")
    (tmp_path / "medium.txt").write_text("ab", encoding="utf-8")
    (tmp_path / "large.txt").write_text("abc", encoding="utf-8")
    service = build_service(tmp_path)

    entries, _ = service.list_directory(
        "/", sort="size,asc", show_hidden=True
    )
    assert [entry.name for entry in entries] == [
        "small.txt",
        "medium.txt",
        "large.txt",
    ]


def test_list_directory_filter_directory(tmp_path: Path) -> None:
    """``filter_type='directory'`` 时仅返回目录。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    service = build_service(tmp_path)

    entries, total = service.list_directory(
        "/", filter_type="directory", show_hidden=True
    )
    assert total == 1
    assert entries[0].name == "subdir"


def test_list_directory_filter_file(tmp_path: Path) -> None:
    """``filter_type='file'`` 时仅返回文件。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "subdir").mkdir()
    service = build_service(tmp_path)

    entries, total = service.list_directory(
        "/", filter_type="file", show_hidden=True
    )
    assert total == 1
    assert entries[0].name == "a.txt"


def test_list_directory_hides_hidden_when_disabled(tmp_path: Path) -> None:
    """``show_hidden=False`` 时隐藏项目被过滤。"""
    (tmp_path / "visible.txt").write_text("a", encoding="utf-8")
    (tmp_path / ".hidden.txt").write_text("b", encoding="utf-8")
    service = build_service(tmp_path)

    entries, total = service.list_directory("/", show_hidden=False)
    assert total == 1
    assert entries[0].name == "visible.txt"


def test_list_directory_shows_hidden_when_enabled(tmp_path: Path) -> None:
    """``show_hidden=True`` 时隐藏项目被包含。"""
    (tmp_path / "visible.txt").write_text("a", encoding="utf-8")
    (tmp_path / ".hidden.txt").write_text("b", encoding="utf-8")
    service = build_service(tmp_path)

    entries, total = service.list_directory("/", show_hidden=True)
    assert total == 2


def test_list_directory_rejects_nonexistent(tmp_path: Path) -> None:
    """不存在的目录应抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.list_directory("/nonexistent")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_list_directory_rejects_non_directory(tmp_path: Path) -> None:
    """对文件调用列表应抛出 ``NOT_FOUND``。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.list_directory("/a.txt")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_list_directory_rejects_invalid_sort(tmp_path: Path) -> None:
    """非法排序表达式应抛出 ``VALIDATION_ERROR``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.list_directory("/", sort="invalid")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_list_directory_rejects_unknown_sort_field(tmp_path: Path) -> None:
    """不支持的排序字段应抛出 ``VALIDATION_ERROR``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.list_directory("/", sort="unknown,asc")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_list_directory_rejects_unknown_sort_direction(
    tmp_path: Path,
) -> None:
    """不支持的排序方向应抛出 ``VALIDATION_ERROR``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.list_directory("/", sort="name,up")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_list_directory_includes_symlink_as_link(tmp_path: Path) -> None:
    """``follow_link=False`` 时符号链接以 ``link`` 类型列出。"""
    target = tmp_path / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    service = build_service(tmp_path)

    entries, _ = service.list_directory(
        "/", follow_link=False, show_hidden=True
    )
    link_entry = next(entry for entry in entries if entry.name == "link.txt")
    assert link_entry.type == "link"


def test_get_metadata_file(tmp_path: Path) -> None:
    """获取文件元数据应成功。"""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    service = build_service(tmp_path)

    metadata = service.get_metadata("/a.txt")
    assert metadata.name == "a.txt"
    assert metadata.path == "/a.txt"
    assert metadata.type == "file"
    assert metadata.size == 5


def test_get_metadata_directory(tmp_path: Path) -> None:
    """获取目录元数据应成功。"""
    (tmp_path / "docs").mkdir()
    service = build_service(tmp_path)

    metadata = service.get_metadata("/docs")
    assert metadata.type == "directory"
    assert metadata.size == 0
    assert metadata.mime_type is None


def test_get_metadata_nonexistent(tmp_path: Path) -> None:
    """获取不存在路径的元数据应抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.get_metadata("/nonexistent.txt")
    assert exc_info.value.code == ErrorCode.NOT_FOUND
