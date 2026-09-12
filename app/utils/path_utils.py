"""虚拟路径规范化工具。

本模块提供纯字符串层面的虚拟路径处理函数，不涉及任何文件系统
访问，也不依赖沙箱根目录。沙箱边界校验由
:class:`app.services.path_service.PathService` 负责。

虚拟路径的约定：

- 以 ``/`` 开头，表示沙箱内的绝对路径；
- 段之间使用 ``/`` 分隔；
- 不含空字节、``..`` 段、``~`` 段。
"""

from typing import Optional

from ..errors import BusinessError, ErrorCode


ROOT_PATH: str = "/"
"""沙箱虚拟根路径。"""


def normalize_virtual_path(virtual_path: Optional[str]) -> str:
    """将输入路径规范化为沙箱内的绝对虚拟路径。

    规范化规则：

    - ``None``、空字符串或仅含空白的字符串视为根路径 ``/``；
    - 折叠连续分隔符，忽略 ``.`` 段；
    - 强制以 ``/`` 开头；
    - 拒绝 ``..`` 段、``~`` 段与含空字节的段。

    Args:
        virtual_path: 用户输入的虚拟路径，可为 ``None``。

    Returns:
        以 ``/`` 开头的规范化虚拟路径。

    Raises:
        BusinessError: 路径包含 ``..``、``~`` 或空字节。
    """
    if virtual_path is None or virtual_path.strip() == "":
        return ROOT_PATH

    segments: list[str] = []
    for segment in virtual_path.split("/"):
        if segment == "" or segment == ".":
            continue
        if segment == "..":
            raise BusinessError(
                ErrorCode.INVALID_PATH,
                "路径不能包含上级目录引用 '..'",
            )
        if segment == "~":
            raise BusinessError(
                ErrorCode.INVALID_PATH,
                "路径不能包含用户主目录引用 '~'",
            )
        if "\0" in segment:
            raise BusinessError(
                ErrorCode.INVALID_PATH,
                "路径不能包含空字节",
            )
        segments.append(segment)

    if not segments:
        return ROOT_PATH
    return ROOT_PATH + "/".join(segments)


__all__ = ["normalize_virtual_path", "ROOT_PATH"]
