"""文件系统 Schema 单元测试。

覆盖 :class:`FileSystemEntryMetadata` 的序列化行为与
:class:`ListDirectoryQuery` 的默认值、别名、约束校验。
"""

import pytest
from pydantic import ValidationError

from app.constants import (
    DEFAULT_FILTER_TYPE,
    DEFAULT_FOLLOW_LINK,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_FIELD,
    DEFAULT_SORT_ORDER,
    MAX_PAGE_SIZE,
)
from app.schemas.filesystem import (
    FileSystemEntryMetadata,
    ListDirectoryQuery,
)


def build_sample_metadata() -> FileSystemEntryMetadata:
    """构造一个用于测试的元数据实例。

    Returns:
        填满全部字段的 :class:`FileSystemEntryMetadata` 实例。
    """
    return FileSystemEntryMetadata(
        name="report.pdf",
        path="/documents/report.pdf",
        type="file",
        mime_type="application/pdf",
        size=1048576,
        created_at=1789187960.2914314,
        modified_at=1789187960.2914314,
        accessed_at=1789187960.2914314,
        permissions="rw-r--r--",
        is_hidden=False,
    )


def test_metadata_serialization_uses_camel_case() -> None:
    """序列化时应输出小驼峰字段名。"""
    metadata = build_sample_metadata()
    payload = metadata.model_dump(by_alias=True)
    assert payload["mimeType"] == "application/pdf"
    assert payload["createdAt"] == 1789187960.2914314
    assert payload["modifiedAt"] == 1789187960.2914314
    assert payload["accessedAt"] == 1789187960.2914314
    assert payload["isHidden"] is False
    assert "mime_type" not in payload
    assert "created_at" not in payload


def test_metadata_accepts_snake_case_input() -> None:
    """构造时应允许使用下划线命名，便于后端内部直接赋值。"""
    metadata = build_sample_metadata()
    assert metadata.mime_type == "application/pdf"
    assert metadata.created_at == 1789187960.2914314


def test_metadata_accepts_camel_case_input() -> None:
    """构造时应允许使用小驼峰命名，便于从 JSON 反序列化。"""
    metadata = FileSystemEntryMetadata(
        name="a.txt",
        path="/a.txt",
        type="file",
        mimeType="text/plain",
        size=1,
        createdAt=1.0,
        modifiedAt=1.0,
        accessedAt=1.0,
        permissions="rw-r--r--",
        isHidden=False,
    )
    assert metadata.mime_type == "text/plain"
    assert metadata.is_hidden is False


def test_metadata_directory_without_mime_and_zero_size() -> None:
    """目录允许 ``mime_type`` 为 ``None`` 且 ``size`` 为 0。"""
    metadata = FileSystemEntryMetadata(
        name="documents",
        path="/documents",
        type="directory",
        size=0,
        created_at=1.0,
        modified_at=1.0,
        accessed_at=1.0,
        permissions="rwxr-xr-x",
        is_hidden=False,
    )
    assert metadata.mime_type is None


def test_metadata_rejects_negative_size() -> None:
    """``size`` 为负数时应抛出校验错误。"""
    with pytest.raises(ValidationError):
        FileSystemEntryMetadata(
            name="a.txt",
            path="/a.txt",
            type="file",
            size=-1,
            created_at=1.0,
            modified_at=1.0,
            accessed_at=1.0,
            permissions="rw-r--r--",
            is_hidden=False,
        )


def test_metadata_rejects_unknown_type() -> None:
    """``type`` 为未定义取值时应抛出校验错误。"""
    with pytest.raises(ValidationError):
        FileSystemEntryMetadata(
            name="a.txt",
            path="/a.txt",
            type="unknown",
            size=0,
            created_at=1.0,
            modified_at=1.0,
            accessed_at=1.0,
            permissions="rw-r--r--",
            is_hidden=False,
        )


def test_metadata_rejects_extra_field() -> None:
    """未定义字段应被拒绝，避免请求体中混入垃圾数据。"""
    with pytest.raises(ValidationError):
        FileSystemEntryMetadata(
            name="a.txt",
            path="/a.txt",
            type="file",
            size=0,
            created_at=1.0,
            modified_at=1.0,
            accessed_at=1.0,
            permissions="rw-r--r--",
            is_hidden=False,
            unexpectedField="boom",
        )


def test_list_directory_query_defaults() -> None:
    """``ListDirectoryQuery`` 无参构造时应使用全部默认值。"""
    query = ListDirectoryQuery()
    assert query.path == "/"
    assert query.page == DEFAULT_PAGE
    assert query.size == DEFAULT_PAGE_SIZE
    assert query.sort == f"{DEFAULT_SORT_FIELD},{DEFAULT_SORT_ORDER}"
    assert query.type == DEFAULT_FILTER_TYPE
    assert query.follow_link is DEFAULT_FOLLOW_LINK


def test_list_directory_query_accepts_camel_case() -> None:
    """应支持使用 ``followLink`` 别名构造。"""
    query = ListDirectoryQuery(followLink=False)
    assert query.follow_link is False


def test_list_directory_query_rejects_page_below_minimum() -> None:
    """``page`` 小于 1 时应抛出校验错误。"""
    with pytest.raises(ValidationError):
        ListDirectoryQuery(page=0)


def test_list_directory_query_rejects_size_above_maximum() -> None:
    """``size`` 超过上限时应抛出校验错误。"""
    with pytest.raises(ValidationError):
        ListDirectoryQuery(size=MAX_PAGE_SIZE + 1)


def test_list_directory_query_rejects_size_below_minimum() -> None:
    """``size`` 小于 1 时应抛出校验错误。"""
    with pytest.raises(ValidationError):
        ListDirectoryQuery(size=0)


def test_list_directory_query_rejects_invalid_filter_type() -> None:
    """``type`` 为未定义取值时应抛出校验错误。"""
    with pytest.raises(ValidationError):
        ListDirectoryQuery(type="symlink")


def test_list_directory_query_rejects_extra_field() -> None:
    """未定义查询参数应被拒绝。"""
    with pytest.raises(ValidationError):
        ListDirectoryQuery(unexpectedParameter="boom")
