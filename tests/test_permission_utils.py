"""权限格式化与隐藏属性判断工具单元测试。

覆盖常见权限位组合、边界情况以及隐藏项目判定。
"""

from pathlib import Path

from app.utils.permission_utils import format_permissions, is_hidden


def test_format_permissions_typical_modes() -> None:
    """常见权限位应格式化为预期字符串。"""
    assert format_permissions(0o644) == "rw-r--r--"
    assert format_permissions(0o755) == "rwxr-xr-x"
    assert format_permissions(0o600) == "rw-------"
    assert format_permissions(0o777) == "rwxrwxrwx"
    assert format_permissions(0o700) == "rwx------"
    assert format_permissions(0o400) == "r--------"


def test_format_permissions_zero_and_empty() -> None:
    """权限位全为 0 时应返回全横线。"""
    assert format_permissions(0o000) == "---------"


def test_format_permissions_ignores_file_type_bits() -> None:
    """文件类型位（高位）不应影响格式化结果。"""
    # 0o100644 表示普通文件 + rw-r--r--
    assert format_permissions(0o100644) == "rw-r--r--"
    # 0o040755 表示目录 + rwxr-xr-x
    assert format_permissions(0o040755) == "rwxr-xr-x"


def test_format_permissions_ignores_special_bits() -> None:
    """setuid / setgid / sticky 等特殊位不应影响权限字符串。"""
    # setuid + rwxr-xr-x
    assert format_permissions(0o4755) == "rwxr-xr-x"
    # sticky + rwxrwxrwx
    assert format_permissions(0o1777) == "rwxrwxrwx"


def test_format_permissions_length_is_always_nine() -> None:
    """输出长度恒为 9。"""
    for mode in range(0o000, 0o1000):
        assert len(format_permissions(mode)) == 9


def test_is_hidden_dot_prefix() -> None:
    """以点开头的名称应被视为隐藏项目。"""
    assert is_hidden(".env", Path("/x/.env")) is True
    assert is_hidden(".gitignore", Path("/x/.gitignore")) is True
    assert is_hidden(".config", Path("/x/.config")) is True


def test_is_hidden_normal_name() -> None:
    """普通名称不应被视为隐藏项目。"""
    assert is_hidden("readme.md", Path("/x/readme.md")) is False
    assert is_hidden("documents", Path("/x/documents")) is False


def test_is_hidden_special_names() -> None:
    """特殊名称 ``.``、``..`` 与空串不应被视为隐藏项目。"""
    assert is_hidden(".", Path("/x")) is False
    assert is_hidden("..", Path("/x")) is False
    assert is_hidden("", Path("/x")) is False


def test_is_hidden_dot_inside_name_not_hidden() -> None:
    """点出现在名称中间或结尾时不应视为隐藏。"""
    assert is_hidden("archive.tar.gz", Path("/x/archive.tar.gz")) is False
    assert is_hidden("file.", Path("/x/file.")) is False
