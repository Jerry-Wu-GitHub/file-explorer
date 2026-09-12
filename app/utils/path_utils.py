"""路径校验与沙箱边界解析。

所有用户提供的“文件路径”都是沙箱虚拟绝对路径（以 / 开头）。
本模块负责：校验路径合法性（拒绝 ..、~）、转换为真实操作路径、
并在必要时解析符号链接后再次校验最终真实路径仍在沙箱根目录内。
"""

import os
from pathlib import Path

from app.config import get_config
from app.utils.errors import (
    ForbiddenError,
    InvalidPathError,
    PathOutsideSandboxError,
)


def ensure_sandbox_root() -> Path:
    """确保沙箱根目录存在并返回其真实路径。"""
    root_path: Path = Path(get_config().sandbox_root).expanduser()
    root_path.mkdir(parents=True, exist_ok=True)
    return root_path.resolve()


def validate_relative_path(raw_path: str) -> str:
    """校验并规范化用户提供的虚拟路径，返回以 / 开头的规范路径。

    规则：必须以 / 开头；拒绝任何段为 .. 或 ~、以及包含 ~ 的段。
    """
    if raw_path is None or raw_path == "":
        return "/"

    if not raw_path.startswith("/"):
        raise InvalidPathError("路径必须以 / 开头")

    if "\x00" in raw_path:
        raise InvalidPathError("路径包含非法字符")

    segments: list[str] = raw_path.split("/")
    for segment in segments:
        if segment == "..":
            raise InvalidPathError("路径不允许包含 ..")
        if "~" in segment:
            raise InvalidPathError("路径不允许包含 ~")

    normalized: str = os.path.normpath(raw_path)
    return normalized


def _is_within(candidate: Path, root: Path) -> bool:
    """判断 candidate 是否等于 root 或位于 root 内部。"""
    candidate_text: str = str(candidate)
    root_text: str = str(root)
    return candidate_text == root_text or candidate_text.startswith(root_text + os.sep)


def is_path_within_sandbox(path: Path) -> bool:
    """判断给定真实路径是否仍位于沙箱根目录内。"""
    root: Path = ensure_sandbox_root()
    return _is_within(path.resolve(), root)


def _ensure_ancestors_within(candidate: Path, root: Path) -> None:
    """校验 candidate 最近存在祖先的真实路径仍在沙箱内。

    防止通过沙箱内的符号链接目录访问沙箱外内容（followLink=false 场景）。
    """
    probe: Path = candidate.parent
    while not os.path.exists(probe) and probe != root:
        probe = probe.parent
    real_probe: Path = Path(probe).resolve()
    if not _is_within(real_probe, root):
        raise PathOutsideSandboxError("路径真实位置越出沙箱根目录")


def resolve_path(
    virtual_path: str,
    follow_link: bool,
    *,
    outside_code: str = "FORBIDDEN",
) -> Path:
    """将虚拟路径转换为沙箱内的真实操作路径。

    follow_link=True 时解析全部符号链接，并对最终真实路径做沙箱校验；
    follow_link=False 时不解析路径本身的链接，仅校验父目录链真实位置。
    outside_code 指定越界时的业务错误码（通用接口 FORBIDDEN，
    分片上传接口 PATH_OUTSIDE_SANDBOX）。
    """
    if outside_code not in ("FORBIDDEN", "PATH_OUTSIDE_SANDBOX"):
        raise InvalidPathError("非法的错误码参数")

    root: Path = ensure_sandbox_root()
    relative: str = virtual_path.lstrip("/")
    candidate: Path = Path(os.path.normpath(os.path.join(str(root), relative)))

    if not _is_within(candidate, root):
        if outside_code == "PATH_OUTSIDE_SANDBOX":
            raise PathOutsideSandboxError("路径越出沙箱根目录")
        raise ForbiddenError("路径越出沙箱根目录")

    if follow_link:
        real_path: Path = candidate.resolve()
        if not _is_within(real_path, root):
            if outside_code == "PATH_OUTSIDE_SANDBOX":
                raise PathOutsideSandboxError("最终真实路径越出沙箱根目录")
            raise ForbiddenError("最终真实路径越出沙箱根目录")
        return real_path

    _ensure_ancestors_within(candidate, root)
    return candidate
