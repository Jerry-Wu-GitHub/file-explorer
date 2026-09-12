"""MIME 类型判断工具单元测试。

覆盖目录、常见文件扩展名、补充注册的扩展名、平台差异覆盖以及
未知扩展名的 MIME 类型推断行为。
"""

from pathlib import Path

from app.constants import DEFAULT_MIME_TYPE
from app.utils.mime_utils import guess_mime_type, register_extra_mime_types


def test_guess_mime_type_returns_none_for_directory() -> None:
    """目录应返回 ``None``。"""
    assert guess_mime_type(Path("/sandbox/documents"), True) is None
    assert guess_mime_type(Path("/sandbox"), True) is None


def test_guess_mime_type_common_extensions() -> None:
    """常见扩展名应返回标准库推断出的 MIME 类型。"""
    assert guess_mime_type(Path("/x/a.pdf"), False) == "application/pdf"
    assert guess_mime_type(Path("/x/a.txt"), False) == "text/plain"
    assert guess_mime_type(Path("/x/a.html"), False) == "text/html"
    assert guess_mime_type(Path("/x/a.png"), False) == "image/png"
    assert guess_mime_type(Path("/x/a.jpg"), False) == "image/jpeg"
    assert guess_mime_type(Path("/x/a.json"), False) == "application/json"


def test_guess_mime_type_extra_registered_extensions() -> None:
    """补充注册的扩展名应返回预期的 MIME 类型。"""
    assert guess_mime_type(Path("/x/a.md"), False) == "text/markdown"
    assert guess_mime_type(Path("/x/a.markdown"), False) == "text/markdown"
    assert guess_mime_type(Path("/x/a.yaml"), False) == "application/yaml"
    assert guess_mime_type(Path("/x/a.yml"), False) == "application/yaml"
    assert guess_mime_type(Path("/x/a.toml"), False) == "application/toml"
    assert guess_mime_type(Path("/x/a.webp"), False) == "image/webp"
    assert guess_mime_type(Path("/x/a.avif"), False) == "image/avif"
    assert guess_mime_type(Path("/x/a.wasm"), False) == "application/wasm"


def test_guess_mime_type_overrides_platform_specific_values() -> None:
    """显式覆盖的扩展名应在各平台上返回一致结果。

    Windows 注册表可能把 ``.zip`` 映射为
    ``application/x-zip-compressed``，本用例确保覆盖后返回标准的
    ``application/zip``。
    """
    assert guess_mime_type(Path("/x/a.zip"), False) == "application/zip"
    assert guess_mime_type(Path("/x/a.js"), False) == "text/javascript"
    assert guess_mime_type(Path("/x/a.mjs"), False) == "text/javascript"


def test_guess_mime_type_unknown_extension_falls_back() -> None:
    """未知扩展名应回退到默认 MIME 类型。"""
    assert (
        guess_mime_type(Path("/x/a.this-extension-should-not-exist"), False)
        == DEFAULT_MIME_TYPE
    )


def test_guess_mime_type_without_extension_falls_back() -> None:
    """无扩展名的文件应回退到默认 MIME 类型。"""
    assert guess_mime_type(Path("/x/Makefile"), False) == DEFAULT_MIME_TYPE


def test_register_extra_mime_types_is_idempotent() -> None:
    """重复注册补充 MIME 类型不应产生副作用。"""
    register_extra_mime_types()
    register_extra_mime_types()
    assert guess_mime_type(Path("/x/a.md"), False) == "text/markdown"
    assert guess_mime_type(Path("/x/a.zip"), False) == "application/zip"
