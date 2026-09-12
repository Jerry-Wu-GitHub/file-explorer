"""MIME 类型判断工具。

本模块提供基于文件路径与条目类型的 MIME 猜测函数。目录没有
MIME 类型，返回 ``None``；文件使用标准库 :mod:`mimetypes` 推断，
推断失败时回退到 :data:`app.constants.DEFAULT_MIME_TYPE`。

为消除平台差异（例如 Windows 注册表把 ``.zip`` 映射为
``application/x-zip-compressed``），本模块在导入时用
:data:`_EXTRA_MIME_TYPES` 显式覆盖部分常见扩展名。
"""

import mimetypes
from pathlib import Path
from typing import Optional

from app.constants import DEFAULT_MIME_TYPE


# 显式覆盖或补充的扩展名到 MIME 的映射表。
# 覆盖项优先于系统内置与注册表推断结果，用于消除平台差异。
_EXTRA_MIME_TYPES: dict[str, str] = {
    ".zip": "application/zip",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".wasm": "application/wasm",
}
"""标准库之外需要覆盖或补充的扩展名到 MIME 的映射表。"""


def register_extra_mime_types() -> None:
    """将补充的 MIME 类型注册到标准库中。

    该函数设计为幂等，重复调用不会产生副作用。仅在模块导入时
    调用一次即可。

    注意：``mimetypes.add_type`` 会把新映射加入到 ``types_map``，
    从而覆盖系统注册表推断的旧值。
    """
    for suffix, mime_type in _EXTRA_MIME_TYPES.items():
        mimetypes.add_type(mime_type, suffix)


register_extra_mime_types()


def guess_mime_type(real_path: Path, is_directory: bool) -> Optional[str]:
    """猜测给定文件或目录的 MIME 类型。

    Args:
        real_path: 文件或目录的真实路径。
        is_directory: 该路径是否表示目录。

    Returns:
        目录返回 ``None``；文件返回推断出的 MIME 类型；若无法推断
        则回退到 :data:`app.constants.DEFAULT_MIME_TYPE`。
    """
    if is_directory:
        return None
    mime_type, _ = mimetypes.guess_type(str(real_path))
    if mime_type is None or mime_type == "":
        return DEFAULT_MIME_TYPE
    return mime_type


__all__ = ["guess_mime_type", "register_extra_mime_types"]
