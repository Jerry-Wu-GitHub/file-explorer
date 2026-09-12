"""权限字符串与数字模式之间的转换。"""

import os
import stat
from typing import Optional

from app.utils.errors import ValidationFailedError

_MODE_SPECS: list[tuple[int, str]] = [
    (stat.S_IRUSR, "r"),
    (stat.S_IWUSR, "w"),
    (stat.S_IXUSR, "x"),
    (stat.S_IRGRP, "r"),
    (stat.S_IWGRP, "w"),
    (stat.S_IXGRP, "x"),
    (stat.S_IROTH, "r"),
    (stat.S_IWOTH, "w"),
    (stat.S_IXOTH, "x"),
]


def mode_to_permissions(mode: int) -> str:
    """将 st_mode 转换为形如 rwxr-xr-x 的权限字符串。"""
    result: list[str] = []
    for flag, char in _MODE_SPECS:
        result.append(char if mode & flag else "-")
    return "".join(result)


def permissions_to_mode(permissions: str) -> int:
    """将权限字符串解析为数字模式，非法输入抛出校验错误。"""
    if len(permissions) != 9:
        raise ValidationFailedError("权限字符串必须为 9 个字符")

    mode: int = 0
    for index, flag in enumerate(_MODE_SPECS):
        character: str = permissions[index]
        if character == flag[1]:
            mode |= flag[0]
        elif character != "-":
            raise ValidationFailedError(f"权限字符串包含非法字符: {character}")
    return mode


def apply_permissions(path: str, permissions: str) -> None:
    """将权限字符串应用到目标路径（chmod）。"""
    mode: int = permissions_to_mode(permissions)
    os.chmod(path, mode)


def parse_optional_permissions(permissions: Optional[str]) -> Optional[int]:
    """解析可选的权限字符串，返回数字模式或 None。"""
    if permissions is None:
        return None
    return permissions_to_mode(permissions)
