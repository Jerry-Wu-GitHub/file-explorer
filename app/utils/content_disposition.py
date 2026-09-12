"""Content-Disposition 响应头构造工具。

本模块根据文件名生成符合 RFC 6266 的 ``Content-Disposition`` 值。
纯 ASCII 文件名使用简单形式；包含非 ASCII 字符时使用 RFC 5987
编码。
"""

from urllib.parse import quote


def build_content_disposition(filename: str, inline: bool = False) -> str:
    """构造 ``Content-Disposition`` 响应头。

    Args:
        filename: 文件名。
        inline: 为 ``True`` 时使用 ``inline`` 语义，否则使用
            ``attachment``（默认，提示下载）。

    Returns:
        完整的 ``Content-Disposition`` 头值。
    """
    disposition_type = "inline" if inline else "attachment"
    escaped = escape_ascii_filename(filename)
    if escaped is not None:
        return f'{disposition_type}; filename="{escaped}"'
    encoded = quote(filename, safe="")
    return f"{disposition_type}; filename*=UTF-8''{encoded}"


def escape_ascii_filename(filename: str) -> str | None:
    """若文件名可 ASCII 编码则转义并返回，否则返回 ``None``。

    转义 ``"`` 与 ``\\`` 以避免破坏头结构。

    Args:
        filename: 文件名。

    Returns:
        ASCII 文件名或其转义形式；不可编码时返回 ``None``。
    """
    try:
        filename.encode("ascii")
    except UnicodeEncodeError:
        return None
    return filename.replace("\\", "\\\\").replace('"', '\\"')


__all__ = ["build_content_disposition", "escape_ascii_filename"]
