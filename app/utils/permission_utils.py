"""文件权限与隐藏属性工具。

本模块提供将 POSIX 权限位格式化为 ``rwxr-xr-x`` 形式的函数、
将同格式字符串解析回权限位的函数，以及判断某个目录条目是否应
被视为隐藏项目的函数。

隐藏项目判定以文件名是否以 ``.`` 开头为准，符合 Linux 约定。
"""

from pathlib import Path

from app.constants import HIDDEN_FILE_PREFIX
from app.errors import BusinessError, ErrorCode


PERMISSION_READ_BIT: int = 0o4
"""读权限位。"""

PERMISSION_WRITE_BIT: int = 0o2
"""写权限位。"""

PERMISSION_EXECUTE_BIT: int = 0o1
"""执行权限位。"""

PERMISSION_GROUP_SHIFTS: tuple[int, ...] = (6, 3, 0)
"""所有者、用户组、其他用户三组权限在 mode 中的右移位数。"""

PERMISSION_STRING_LENGTH: int = 9
"""权限字符串长度，固定为 9。"""


def format_permissions(mode: int) -> str:
    """将 ``st_mode`` 权限位格式化为 ``rwxr-xr-x`` 形式的字符串。

    只考虑权限位部分（低 9 位），忽略文件类型位与 setuid 等特殊位。

    Args:
        mode: 来自 ``os.stat_result.st_mode`` 的权限位整数。

    Returns:
        长度为 9 的权限字符串，例如 ``rw-r--r--``。
    """
    characters: list[str] = []
    for shift in PERMISSION_GROUP_SHIFTS:
        group_bits = (mode >> shift) & 0o7
        characters.append("r" if group_bits & PERMISSION_READ_BIT else "-")
        characters.append("w" if group_bits & PERMISSION_WRITE_BIT else "-")
        characters.append("x" if group_bits & PERMISSION_EXECUTE_BIT else "-")
    return "".join(characters)


def parse_permissions_string(permissions: str) -> int:
    """将 ``rwxr-xr-x`` 形式的权限字符串解析为权限位整数。

    Args:
        permissions: 长度为 9 的权限字符串。

    Returns:
        与权限字符串对应的整数权限位，例如 ``0o755``。

    Raises:
        BusinessError: 字符串长度错误或包含非法字符。
    """
    if len(permissions) != PERMISSION_STRING_LENGTH:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"权限字符串必须为 {PERMISSION_STRING_LENGTH} 个字符：'{permissions}'",
        )

    mode = 0
    for group_index in range(3):
        base = group_index * 3
        group = permissions[base : base + 3]
        group_bits = read_permission_group_bits(group)
        mode = (mode << 3) | group_bits
    return mode


def read_permission_group_bits(group: str) -> int:
    """解析单组三字符权限（如 ``rwx``）为三位八进制位。

    Args:
        group: 形如 ``rwx``、``r-x``、``---`` 的三字符字符串。

    Returns:
        该组权限对应的三位八进制位。

    Raises:
        BusinessError: 组内包含非法字符。
    """
    bits = 0
    if group[0] == "r":
        bits |= PERMISSION_READ_BIT
    elif group[0] != "-":
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"权限字符串包含非法字符：'{group[0]}'",
        )
    if group[1] == "w":
        bits |= PERMISSION_WRITE_BIT
    elif group[1] != "-":
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"权限字符串包含非法字符：'{group[1]}'",
        )
    if group[2] == "x":
        bits |= PERMISSION_EXECUTE_BIT
    elif group[2] != "-":
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            f"权限字符串包含非法字符：'{group[2]}'",
        )
    return bits


def is_hidden(name: str, real_path: Path) -> bool:
    """判断某个目录条目是否为隐藏项目。

    以 ``.`` 开头的名称被视为隐藏项目，与 Linux 约定一致。
    ``real_path`` 目前仅作为扩展位保留，方便后续支持基于文件系统
    属性的判定逻辑，本函数当前不使用该参数。

    Args:
        name: 条目名称（不含路径分隔符）。
        real_path: 条目的真实路径，预留给未来扩展。

    Returns:
        若条目为隐藏项目则返回 ``True``，否则返回 ``False``。
    """
    del real_path  # 当前实现仅依据名称判定，保留参数以便未来扩展。
    if name in {"", ".", ".."}:
        return False
    return name.startswith(HIDDEN_FILE_PREFIX)


__all__ = [
    "format_permissions",
    "parse_permissions_string",
    "read_permission_group_bits",
    "is_hidden",
]
