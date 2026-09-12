"""``parse_permissions_string`` 单元测试。

覆盖常见权限字符串、边界情况与非法输入，确保与
:func:`app.utils.permission_utils.format_permissions` 互为逆运算。
"""

import pytest

from app.errors import BusinessError, ErrorCode
from app.utils.permission_utils import (
    format_permissions,
    parse_permissions_string,
    read_permission_group_bits,
)


def test_parse_permissions_typical_strings() -> None:
    """常见权限字符串应解析为正确的八进制权限位。"""
    assert parse_permissions_string("rw-r--r--") == 0o644
    assert parse_permissions_string("rwxr-xr-x") == 0o755
    assert parse_permissions_string("rw-------") == 0o600
    assert parse_permissions_string("rwxrwxrwx") == 0o777
    assert parse_permissions_string("---------") == 0o000


def test_parse_permissions_roundtrip_with_format() -> None:
    """解析与格式化应互为逆运算。"""
    for mode in (0o644, 0o755, 0o600, 0o400, 0o777, 0o000, 0o640):
        assert parse_permissions_string(format_permissions(mode)) == mode


def test_parse_permissions_rejects_wrong_length() -> None:
    """长度不为 9 时应抛出 ``VALIDATION_ERROR``。"""
    with pytest.raises(BusinessError) as exc_info:
        parse_permissions_string("rwx")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_parse_permissions_rejects_invalid_characters() -> None:
    """含非法字符时应抛出 ``VALIDATION_ERROR``。"""
    with pytest.raises(BusinessError) as exc_info:
        parse_permissions_string("rwsr-xr-x")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    with pytest.raises(BusinessError) as exc_info:
        parse_permissions_string("123456789")
    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


def test_read_permission_group_bits() -> None:
    """单组解析应返回三位八进制位。"""
    assert read_permission_group_bits("rwx") == 0o7
    assert read_permission_group_bits("rw-") == 0o6
    assert read_permission_group_bits("r-x") == 0o5
    assert read_permission_group_bits("r--") == 0o4
    assert read_permission_group_bits("-wx") == 0o3
    assert read_permission_group_bits("-w-") == 0o2
    assert read_permission_group_bits("--x") == 0o1
    assert read_permission_group_bits("---") == 0o0
