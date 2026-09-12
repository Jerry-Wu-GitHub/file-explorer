"""文件分块读取工具。

本模块提供按字节范围流式读取文件的生成器函数，供内容下载接口
构造 ``StreamingResponse`` 使用。
"""

from pathlib import Path
from typing import Iterator


DEFAULT_STREAM_CHUNK_SIZE: int = 1024 * 1024
"""默认的流式读取块大小（1 MiB）。"""


def iter_file_range(
    real_path: Path,
    start: int,
    end: int,
    chunk_size: int = DEFAULT_STREAM_CHUNK_SIZE,
) -> Iterator[bytes]:
    """按字节范围流式读取文件。

    起止均包含。当 ``end < start`` 时不产出任何数据，用于空文件
    或空范围场景。

    Args:
        real_path: 目标文件的真实路径。
        start: 起始字节偏移，包含。
        end: 结束字节偏移，包含。
        chunk_size: 每次读取的块大小。

    Yields:
        文件内容的字节块。
    """
    if end < start:
        return
    with real_path.open("rb") as file_handle:
        file_handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            read_size = min(chunk_size, remaining)
            data = file_handle.read(read_size)
            if not data:
                break
            remaining -= len(data)
            yield data


__all__ = ["iter_file_range", "DEFAULT_STREAM_CHUNK_SIZE"]
