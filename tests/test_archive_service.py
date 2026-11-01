"""ArchiveService 单元测试。

覆盖单文件、多文件、目录递归、空目录、符号链接、空列表与错误
路径。符号链接用例在 Windows 上默认跳过。
"""

import io
import sys
import zipfile
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.services.archive_service import (
    ArchiveEntry,
    ArchiveService,
    build_archive_name,
    iter_archive_stream,
)
from app.services.path_service import PathService


SYMLINK_SKIP_REASON = "Windows 创建符号链接需要管理员权限或开发者模式"
"""符号链接用例在 Windows 上跳过的原因说明。"""


def build_service(sandbox: Path) -> ArchiveService:
    """构造使用指定沙箱根目录的 :class:`ArchiveService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的归档服务实例。
    """
    config = Config(sandbox_root=sandbox)
    return ArchiveService(PathService(config))


def read_zip_bytes(data: bytes) -> zipfile.ZipFile:
    """将 ZIP 字节解析为 :class:`zipfile.ZipFile`。

    Args:
        data: ZIP 字节。

    Returns:
        打开的内存 ZIP 对象。
    """
    return zipfile.ZipFile(io.BytesIO(data))


def test_prepare_entries_single_file(tmp_path: Path) -> None:
    """单文件输入应返回一个条目。"""
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/notes.txt"])
    assert len(entries) == 1
    assert entries[0].archive_name == "notes.txt"


def test_prepare_entries_nested_file_keeps_structure(
    tmp_path: Path,
) -> None:
    """嵌套文件的归档名保留输入目录结构。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "report.pdf").write_bytes(b"%PDF-1.4")
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/docs/report.pdf"])
    assert entries[0].archive_name == "docs/report.pdf"


def test_prepare_entries_multiple_files(tmp_path: Path) -> None:
    """多个文件输入应返回多个条目且顺序一致。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/a.txt", "/b.txt"])
    assert [entry.archive_name for entry in entries] == ["a.txt", "b.txt"]


def test_prepare_entries_directory_recursive(tmp_path: Path) -> None:
    """目录输入应递归展开为所有文件。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "src" / "nested").mkdir()
    (tmp_path / "src" / "nested" / "b.txt").write_text("b", encoding="utf-8")
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/src"])
    names = sorted(entry.archive_name for entry in entries)
    assert names == ["src/a.txt", "src/nested/b.txt"]


def test_prepare_entries_directory_with_nested_deep(
    tmp_path: Path,
) -> None:
    """多层嵌套目录应全部递归包含。"""
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_text("x", encoding="utf-8")
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/a"])
    assert entries[0].archive_name == "a/b/c/file.txt"


def test_prepare_archive_deep_file_uses_common_directory_as_root(
    tmp_path: Path,
) -> None:
    """深层文件应以所在目录名作为 ZIP 最外层目录。"""
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_text("x", encoding="utf-8")
    service = build_service(tmp_path)

    plan = service.prepare_archive(["/a/b/c/file.txt"])
    assert plan.root_name == "c"
    assert plan.filename == "c.zip"
    assert [entry.archive_name for entry in plan.entries] == ["c/file.txt"]


def test_prepare_archive_multiple_files_use_deepest_common_directory(
    tmp_path: Path,
) -> None:
    """多个文件应以最深公共目录为根，并保留其下的相对结构。"""
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "a" / "b" / "other.txt").write_text(
        "y", encoding="utf-8"
    )
    service = build_service(tmp_path)

    plan = service.prepare_archive(
        ["/a/b/c/file.txt", "/a/b/other.txt"]
    )
    assert plan.root_name == "b"
    assert plan.filename == "b.zip"
    assert sorted(entry.archive_name for entry in plan.entries) == [
        "b/c/file.txt",
        "b/other.txt",
    ]


def test_prepare_archive_deep_directory_uses_directory_name_as_root(
    tmp_path: Path,
) -> None:
    """深层目录应以该目录名作为 ZIP 最外层目录。"""
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_text("x", encoding="utf-8")
    service = build_service(tmp_path)

    plan = service.prepare_archive(["/a/b/c"])
    assert plan.root_name == "c"
    assert plan.filename == "c.zip"
    assert [entry.archive_name for entry in plan.entries] == ["c/file.txt"]


def test_prepare_archive_root_common_directory_has_no_prefix(
    tmp_path: Path,
) -> None:
    """公共目录为沙箱根目录时不额外添加外层目录。"""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_text("x", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "y.txt").write_text("y", encoding="utf-8")
    service = build_service(tmp_path)

    plan = service.prepare_archive(["/a/x.txt", "/b/y.txt"])
    assert plan.root_name == ""
    assert plan.filename == "archive.zip"
    assert sorted(entry.archive_name for entry in plan.entries) == [
        "a/x.txt",
        "b/y.txt",
    ]


def test_prepare_entries_empty_directory(tmp_path: Path) -> None:
    """空目录返回空条目列表。"""
    (tmp_path / "empty").mkdir()
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/empty"])
    assert entries == []


def test_prepare_entries_mixed_files_and_directory(tmp_path: Path) -> None:
    """文件与目录混合输入应合并条目。"""
    (tmp_path / "root.txt").write_text("r", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("a", encoding="utf-8")
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/root.txt", "/src"])
    names = sorted(entry.archive_name for entry in entries)
    assert names == ["root.txt", "src/a.txt"]


def test_prepare_entries_rejects_empty_list(tmp_path: Path) -> None:
    """空列表应抛出 ``VALIDATION_ERROR``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.prepare_entries([])
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_prepare_entries_rejects_root(tmp_path: Path) -> None:
    """直接打包沙箱根目录应被拒绝。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.prepare_entries(["/"])
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_prepare_entries_rejects_nonexistent(tmp_path: Path) -> None:
    """不存在的路径应抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.prepare_entries(["/missing.txt"])
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_prepare_entries_rejects_parent_reference(tmp_path: Path) -> None:
    """含 ``..`` 的路径应抛出 ``INVALID_PATH``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.prepare_entries(["/../etc/passwd"])
    assert exc_info.value.code == ErrorCode.INVALID_PATH


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_prepare_entries_includes_symlink_target(tmp_path: Path) -> None:
    """``follow_link=True`` 时符号链接作为其目标文件打包。"""
    target = tmp_path / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    service = build_service(tmp_path)

    entries = service.prepare_entries(["/link.txt"], follow_link=True)
    assert len(entries) == 1
    assert entries[0].archive_name == "link.txt"


def test_build_archive_name_at_top_level() -> None:
    """顶层文件的归档名只有基础名 + 文件名。"""
    name = build_archive_name("src", Path("."), "a.txt")
    assert name == "src/a.txt"


def test_build_archive_name_with_subdirectory() -> None:
    """子目录文件包含子目录路径。"""
    name = build_archive_name("src", Path("nested/deep"), "a.txt")
    assert name == "src/nested/deep/a.txt"


def test_iter_archive_stream_produces_valid_zip(tmp_path: Path) -> None:
    """生成的字节流应为合法 ZIP，且内容与源文件一致。"""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "b.txt").write_text("world", encoding="utf-8")
    service = build_service(tmp_path)
    entries = service.prepare_entries(["/a.txt", "/docs"])

    data = b"".join(iter_archive_stream(entries))
    with read_zip_bytes(data) as archive:
        names = sorted(archive.namelist())
        assert names == ["a.txt", "docs/b.txt"]
        assert archive.read("a.txt") == b"hello"
        assert archive.read("docs/b.txt") == b"world"


def test_iter_archive_stream_empty_entries(tmp_path: Path) -> None:
    """空条目列表应生成合法但空的 ZIP。"""
    data = b"".join(iter_archive_stream([]))
    with read_zip_bytes(data) as archive:
        assert archive.namelist() == []


def test_archive_entry_is_frozen(tmp_path: Path) -> None:
    """``ArchiveEntry`` 应为不可变对象。"""
    entry = ArchiveEntry(real_path=tmp_path / "x", archive_name="x")
    with pytest.raises(Exception):
        entry.archive_name = "y"  # type: ignore[misc]
