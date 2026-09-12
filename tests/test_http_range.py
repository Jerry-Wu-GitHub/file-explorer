"""HTTP Range 解析单元测试。

覆盖 ABSENT / VALID / INVALID 三类状态以及闭区间、开区间、后缀
区间和越界处理。
"""

from app.utils.http_range import (
    RangeRequest,
    RangeStatus,
    parse_range_header,
)


def test_absent_when_header_missing_or_empty() -> None:
    """未提供 Range 头或值为空时状态为 ``ABSENT``。"""
    assert parse_range_header(None, 1000).status == RangeStatus.ABSENT
    assert parse_range_header("", 1000).status == RangeStatus.ABSENT
    assert parse_range_header("   ", 1000).status == RangeStatus.ABSENT


def test_invalid_when_prefix_wrong() -> None:
    """非 ``bytes=`` 前缀应视为无效。"""
    assert parse_range_header("items=0-99", 1000).status == RangeStatus.INVALID
    assert parse_range_header("0-99", 1000).status == RangeStatus.INVALID


def test_closed_range() -> None:
    """``bytes=0-99`` 解析为闭区间。"""
    result = parse_range_header("bytes=0-99", 1000)
    assert result.status == RangeStatus.VALID
    assert result.request == RangeRequest(start=0, end=99)


def test_closed_range_clamps_to_file_end() -> None:
    """``end`` 超过文件末尾时被截断为文件末尾。"""
    result = parse_range_header("bytes=900-9999", 1000)
    assert result.status == RangeStatus.VALID
    assert result.request == RangeRequest(start=900, end=999)


def test_open_ended_range() -> None:
    """``bytes=500-`` 表示从 500 到文件末尾。"""
    result = parse_range_header("bytes=500-", 1000)
    assert result.status == RangeStatus.VALID
    assert result.request == RangeRequest(start=500, end=999)


def test_suffix_range() -> None:
    """``bytes=-100`` 表示文件末尾 100 字节。"""
    result = parse_range_header("bytes=-100", 1000)
    assert result.status == RangeStatus.VALID
    assert result.request == RangeRequest(start=900, end=999)


def test_suffix_range_exceeds_file_size() -> None:
    """suffix 超过文件大小时取整个文件。"""
    result = parse_range_header("bytes=-9999", 1000)
    assert result.status == RangeStatus.VALID
    assert result.request == RangeRequest(start=0, end=999)


def test_suffix_range_zero_is_invalid() -> None:
    """suffix 为 0 时视为无效。"""
    assert parse_range_header("bytes=-0", 1000).status == RangeStatus.INVALID


def test_start_beyond_file_size_is_invalid() -> None:
    """起始位置超过文件大小时视为无效。"""
    assert parse_range_header("bytes=1000-", 1000).status == RangeStatus.INVALID
    assert (
        parse_range_header("bytes=1500-1600", 1000).status
        == RangeStatus.INVALID
    )


def test_end_before_start_is_invalid() -> None:
    """结束位置小于起始位置时视为无效。"""
    assert (
        parse_range_header("bytes=500-100", 1000).status
        == RangeStatus.INVALID
    )


def test_multi_range_is_invalid() -> None:
    """多范围请求视为无效。"""
    assert (
        parse_range_header("bytes=0-99,200-299", 1000).status
        == RangeStatus.INVALID
    )


def test_non_numeric_values_are_invalid() -> None:
    """非数字参数视为无效。"""
    assert parse_range_header("bytes=a-b", 1000).status == RangeStatus.INVALID
    assert parse_range_header("bytes=abc-", 1000).status == RangeStatus.INVALID
    assert parse_range_header("bytes=-xyz", 1000).status == RangeStatus.INVALID


def test_empty_file_any_range_is_invalid() -> None:
    """空文件（total_size=0）时任何范围都视为无效。"""
    assert parse_range_header("bytes=0-", 0).status == RangeStatus.INVALID
    assert parse_range_header("bytes=-10", 0).status == RangeStatus.INVALID
