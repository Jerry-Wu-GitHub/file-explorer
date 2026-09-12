"""文件内容下载服务。

本模块提供 :class:`ContentService`，负责准备内容下载所需的全部
信息：真实路径、文件大小、MIME 类型、ETag、Last-Modified 以及
Range 解析结果。路由层据此构造流式响应。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..errors import BusinessError, ErrorCode
from .path_service import PathService
from ..utils.http_range import (
    RangeParseResult,
    RangeStatus,
    parse_range_header,
)
from ..utils.mime_utils import guess_mime_type


@dataclass(frozen=True)
class ContentDescriptor:
    """内容下载的完整描述信息。

    用于路由层构造 200 / 206 / 416 三种响应。
    """

    real_path: Path
    """目标文件的真实路径。"""

    filename: str
    """用于 Content-Disposition 的文件名。"""

    file_size: int
    """文件总字节数。"""

    mime_type: str
    """文件 MIME 类型。"""

    etag: str
    """文件 ETag 值，包含引号。"""

    last_modified: float
    """文件修改时间（Unix 时间戳，单位：秒）。"""

    range_result: RangeParseResult
    """Range 解析结果。"""


class ContentService:
    """文件内容下载服务。

    Attributes:
        path_service: 沙箱路径解析服务。
    """

    def __init__(self, path_service: PathService) -> None:
        """构造内容服务。

        Args:
            path_service: 沙箱路径解析服务。
        """
        self._path_service: PathService = path_service

    def prepare_content(
        self,
        virtual_path: str,
        follow_link: bool,
        range_header: Optional[str],
    ) -> ContentDescriptor:
        """准备内容下载所需的全部描述信息。

        Args:
            virtual_path: 目标文件的沙箱虚拟路径。
            follow_link: 是否跟随符号链接。
            range_header: ``Range`` 请求头的原始值，可为 ``None``。

        Returns:
            内容描述对象。

        Raises:
            BusinessError: 路径非法、目标不存在或不是常规文件。
        """
        real_path = self._path_service.resolve_real_path(
            virtual_path, follow_link=follow_link
        )
        if not real_path.exists() or not real_path.is_file():
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                f"文件不存在：{virtual_path}",
            )

        try:
            stat_result = real_path.stat()
        except OSError as exc:
            raise BusinessError(
                ErrorCode.INTERNAL_ERROR,
                f"读取文件信息失败：{real_path.name}",
            ) from exc

        file_size = stat_result.st_size
        mime_type = guess_mime_type(real_path, False) or "application/octet-stream"
        etag = build_etag(stat_result.st_mtime_ns, file_size)
        range_result = parse_range_header(range_header, file_size)

        return ContentDescriptor(
            real_path=real_path,
            filename=real_path.name,
            file_size=file_size,
            mime_type=mime_type,
            etag=etag,
            last_modified=stat_result.st_mtime,
            range_result=range_result,
        )


def build_etag(mtime_ns: int, size: int) -> str:
    """根据纳秒级修改时间与文件大小生成 ETag。

    Args:
        mtime_ns: ``st_mtime_ns`` 值。
        size: 文件大小。

    Returns:
        形如 ``"1a2b3c-4d5e6f"`` 的 ETag 字符串，包含引号。
    """
    return f'"{mtime_ns:x}-{size:x}"'


__all__ = ["ContentService", "ContentDescriptor", "build_etag"]
