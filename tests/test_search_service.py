"""SearchService 单元测试。

覆盖递归搜索、关键词、类型、大小、时间过滤、分页、空结果与
错误路径。
"""

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.schemas.search import SearchQuery
from app.services.metadata_service import MetadataService
from app.services.path_service import PathService
from app.services.search_service import SearchService


def build_service(sandbox: Path) -> SearchService:
    """构造使用指定沙箱根目录的 :class:`SearchService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的搜索服务实例。
    """
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    return SearchService(path_service, MetadataService(path_service))


def prepare_tree(sandbox: Path) -> None:
    """准备一棵用于搜索的固定目录树。

    结构（共 8 个条目）：

    - /root.txt（5 字节，文件）
    - /docs/（目录）
    - /docs/report.pdf（10 字节，文件）
    - /docs/notes.md（3 字节，文件）
    - /docs/archive/（目录）
    - /docs/archive/old.txt（100 字节，文件）
    - /images/（目录）
    - /images/photo.png（8 字节，文件）
    """
    (sandbox / "root.txt").write_bytes(b"hello")
    (sandbox / "docs").mkdir()
    (sandbox / "docs" / "report.pdf").write_bytes(b"%PDF-1.4aa")
    (sandbox / "docs" / "notes.md").write_bytes(b"abc")
    (sandbox / "docs" / "archive").mkdir()
    (sandbox / "docs" / "archive" / "old.txt").write_bytes(b"x" * 100)
    (sandbox / "images").mkdir()
    (sandbox / "images" / "photo.png").write_bytes(b"12345678")


def test_search_all_entries(tmp_path: Path) -> None:
    """无条件搜索应返回整棵树的所有条目（共 8 个）。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery())
    assert total == 8
    names = sorted(entry.name for entry in entries)
    assert names == [
        "archive",
        "docs",
        "images",
        "notes.md",
        "old.txt",
        "photo.png",
        "report.pdf",
        "root.txt",
    ]


def test_search_by_keyword(tmp_path: Path) -> None:
    """关键词应做不区分大小写的子串匹配。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(q="REPORT"))
    assert total == 1
    assert entries[0].name == "report.pdf"


def test_search_by_keyword_matches_partial(tmp_path: Path) -> None:
    """部分匹配应命中多个条目。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(q=".txt"))
    assert total == 2
    names = sorted(entry.name for entry in entries)
    assert names == ["old.txt", "root.txt"]


def test_search_filter_by_type_file(tmp_path: Path) -> None:
    """``type=file`` 时只返回文件（共 5 个）。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(type="file"))
    assert total == 5
    assert all(entry.type == "file" for entry in entries)


def test_search_filter_by_type_directory(tmp_path: Path) -> None:
    """``type=directory`` 时只返回目录（共 3 个）。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(type="directory"))
    assert total == 3
    names = sorted(entry.name for entry in entries)
    assert names == ["archive", "docs", "images"]


def test_search_filter_by_min_size(tmp_path: Path) -> None:
    """``minSize`` 应过滤掉小于该值的条目。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(min_size=50))
    assert total == 1
    assert entries[0].name == "old.txt"


def test_search_filter_by_max_size(tmp_path: Path) -> None:
    """``maxSize`` 应过滤掉大于该值的条目。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(type="file", max_size=5))
    assert total == 2
    names = sorted(entry.name for entry in entries)
    assert names == ["notes.md", "root.txt"]


def test_search_filter_by_size_range(tmp_path: Path) -> None:
    """``minSize`` 与 ``maxSize`` 应同时生效。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(
        SearchQuery(type="file", min_size=4, max_size=10)
    )
    assert total == 3
    names = sorted(entry.name for entry in entries)
    assert names == ["photo.png", "report.pdf", "root.txt"]


def test_search_filter_by_modified_after(tmp_path: Path) -> None:
    """``modifiedAfter`` 应过滤掉更早的条目（共 7 个）。"""
    prepare_tree(tmp_path)
    old_file = tmp_path / "docs" / "archive" / "old.txt"
    old_time = time.time() - 86400
    os.utime(old_file, (old_time, old_time))
    service = build_service(tmp_path)

    after = datetime.now(timezone.utc) - timedelta(hours=1)
    entries, total = service.search(SearchQuery(modified_after=after))
    assert total == 7
    assert all(entry.name != "old.txt" for entry in entries)


def test_search_filter_by_modified_before(tmp_path: Path) -> None:
    """``modifiedBefore`` 应过滤掉更新的条目。"""
    prepare_tree(tmp_path)
    old_file = tmp_path / "docs" / "archive" / "old.txt"
    old_time = time.time() - 86400
    os.utime(old_file, (old_time, old_time))
    service = build_service(tmp_path)

    before = datetime.now(timezone.utc) - timedelta(hours=1)
    entries, total = service.search(SearchQuery(modified_before=before))
    assert total == 1
    assert entries[0].name == "old.txt"


def test_search_time_naive_treated_as_utc(tmp_path: Path) -> None:
    """naive datetime 应视为 UTC，覆盖整棵树（共 8 个）。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(
        SearchQuery(
            modified_after=datetime(2000, 1, 1),
            modified_before=datetime(2100, 1, 1),
        )
    )
    assert total == 8


def test_search_pagination(tmp_path: Path) -> None:
    """分页应返回正确切片。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(
        SearchQuery(type="file", page=2, size=2)
    )
    assert total == 5
    assert len(entries) == 2
    names = [entry.name for entry in entries]
    assert names == sorted(names, key=lambda name: (name.casefold(), name))


def test_search_within_subdirectory(tmp_path: Path) -> None:
    """``path`` 指定子目录时只在其中搜索。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(path="/docs"))
    assert total == 4
    assert all(entry.path.startswith("/docs/") for entry in entries)


def test_search_empty_result(tmp_path: Path) -> None:
    """无匹配时返回空列表与 0 总数。"""
    prepare_tree(tmp_path)
    service = build_service(tmp_path)

    entries, total = service.search(SearchQuery(q="no-such-keyword"))
    assert entries == []
    assert total == 0


def test_search_rejects_nonexistent_path(tmp_path: Path) -> None:
    """起始路径不存在时抛出 ``NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.search(SearchQuery(path="/missing"))
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_search_rejects_non_directory_path(tmp_path: Path) -> None:
    """起始路径不是目录时抛出 ``NOT_FOUND``。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.search(SearchQuery(path="/a.txt"))
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_search_rejects_parent_reference(tmp_path: Path) -> None:
    """路径含 ``..`` 时抛出 ``INVALID_PATH``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.search(SearchQuery(path="/../etc"))
    assert exc_info.value.code == ErrorCode.INVALID_PATH


def test_search_service_rejects_inverted_size_range(tmp_path: Path) -> None:
    """``minSize`` 大于 ``maxSize`` 时服务层抛出 ``VALIDATION_ERROR``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.search(SearchQuery(min_size=100, max_size=10))
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
