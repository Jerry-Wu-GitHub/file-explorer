"""HTTP Range 请求头解析工具。

本模块负责解析 RFC 7233 定义的 ``Range`` 请求头，并计算有效范围。
当前仅支持单范围请求，多范围请求视为无效，避免引入 multipart
响应复杂度。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


BYTES_PREFIX: str = "bytes="
"""Range 头的前缀，大小写不敏感比较。"""


class RangeStatus(str, Enum):
    """Range 解析结果状态。"""

    ABSENT = "absent"
    """未提供 Range 头，应返回完整文件。"""

    VALID = "valid"
    """提供了有效范围，应返回 206 部分内容。"""

    INVALID = "invalid"
    """提供了无效范围，应返回 416。"""


@dataclass(frozen=True)
class RangeRequest:
    """有效的 Range 范围，起止均包含。"""

    start: int
    """起始字节偏移，包含。"""

    end: int
    """结束字节偏移，包含。"""


@dataclass(frozen=True)
class RangeParseResult:
    """Range 解析结果。"""

    status: RangeStatus
    """解析状态。"""

    request: Optional[RangeRequest] = None
    """解析成功时的范围对象。"""


def parse_range_header(
    header_value: Optional[str],
    total_size: int,
) -> RangeParseResult:
    """解析 ``Range`` 请求头。

    支持的语法：

    - ``bytes=start-end``：闭区间，两端都在范围内时使用；
    - ``bytes=start-``：从 start 到文件末尾；
    - ``bytes=-suffix``：文件末尾 suffix 个字节。

    以下情况视为无效：

    - 不是 ``bytes=`` 前缀；
    - 请求多个范围（含逗号）；
    - 起始大于结束；
    - 起始大于等于文件大小；
    - suffix 小于等于 0。

    Args:
        header_value: Range 头的原始值，可为 ``None``。
        total_size: 目标文件的总字节数。

    Returns:
        解析结果对象。
    """
    if header_value is None or header_value.strip() == "":
        return RangeParseResult(RangeStatus.ABSENT)

    stripped = header_value.strip()
    if not stripped.lower().startswith(BYTES_PREFIX):
        return RangeParseResult(RangeStatus.INVALID)

    ranges_part = stripped[len(BYTES_PREFIX) :].strip()
    if ranges_part == "" or "," in ranges_part:
        return RangeParseResult(RangeStatus.INVALID)

    if "-" not in ranges_part:
        return RangeParseResult(RangeStatus.INVALID)

    start_str, end_str = ranges_part.split("-", 1)
    start_str = start_str.strip()
    end_str = end_str.strip()

    if start_str == "" and end_str == "":
        return RangeParseResult(RangeStatus.INVALID)

    if start_str == "":
        return parse_suffix_range(end_str, total_size)
    return parse_start_range(start_str, end_str, total_size)


def parse_suffix_range(
    suffix_str: str,
    total_size: int,
) -> RangeParseResult:
    """解析 ``bytes=-suffix`` 形式。

    Args:
        suffix_str: 连字符后的数字字符串。
        total_size: 文件总字节数。

    Returns:
        解析结果。
    """
    try:
        suffix = int(suffix_str)
    except ValueError:
        return RangeParseResult(RangeStatus.INVALID)
    if suffix <= 0 or total_size == 0:
        return RangeParseResult(RangeStatus.INVALID)
    if suffix > total_size:
        suffix = total_size
    return RangeParseResult(
        RangeStatus.VALID,
        RangeRequest(start=total_size - suffix, end=total_size - 1),
    )


def parse_start_range(
    start_str: str,
    end_str: str,
    total_size: int,
) -> RangeParseResult:
    """解析 ``bytes=start-`` 与 ``bytes=start-end`` 两种形式。

    Args:
        start_str: 起始字节字符串。
        end_str: 结束字节字符串，可为空。
        total_size: 文件总字节数。

    Returns:
        解析结果。
    """
    try:
        start = int(start_str)
    except ValueError:
        return RangeParseResult(RangeStatus.INVALID)
    if start < 0 or start >= total_size:
        return RangeParseResult(RangeStatus.INVALID)

    if end_str == "":
        return RangeParseResult(
            RangeStatus.VALID,
            RangeRequest(start=start, end=total_size - 1),
        )

    try:
        end = int(end_str)
    except ValueError:
        return RangeParseResult(RangeStatus.INVALID)
    if end < start:
        return RangeParseResult(RangeStatus.INVALID)
    if end >= total_size:
        end = total_size - 1
    return RangeParseResult(
        RangeStatus.VALID,
        RangeRequest(start=start, end=end),
    )


__all__ = [
    "RangeStatus",
    "RangeRequest",
    "RangeParseResult",
    "parse_range_header",
]
