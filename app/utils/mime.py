"""MIME 类型检测。"""

import mimetypes
import os
from typing import Optional

# 常用但标准库缺失的扩展名映射
_EXTRA_MIME_TYPES: dict[str, str] = {
    ".md": "text/markdown",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".toml": "application/toml",
    ".ini": "text/plain",
    ".conf": "text/plain",
    ".log": "text/plain",
    ".env": "text/plain",
    ".ts": "text/typescript",
    ".tsx": "text/typescript",
    ".jsx": "text/javascript",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".epub": "application/epub+zip",
    ".7z": "application/x-7z-compressed",
    ".apk": "application/vnd.android.package-archive",
}


def guess_mime_type(filename: str) -> str:
    """根据文件名猜测 MIME 类型，无法识别时回退为 application/octet-stream。"""
    lower_name: str = filename.lower()
    extension: str = os.path.splitext(lower_name)[1]
    if extension in _EXTRA_MIME_TYPES:
        return _EXTRA_MIME_TYPES[extension]

    guessed: Optional[str] = mimetypes.guess_type(filename)[0]
    return guessed or "application/octet-stream"
