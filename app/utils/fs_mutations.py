"""文件系统变更操作：创建、删除、重命名、复制、属性修改。"""

import os
import posixpath
import shutil
import uuid
from pathlib import Path
from typing import Optional

from app.models.fs_entry import FsEntry
from app.utils.errors import (
    ConflictError,
    ForbiddenError,
    InvalidPathError,
    NotFoundError,
)
from app.utils.fs_utils import build_entry
from app.utils.path_utils import resolve_path, validate_relative_path
from app.utils.permissions import apply_permissions, permissions_to_mode

_UPLOAD_BUFFER_SIZE: int = 1024 * 1024


def _resolve_parent(virtual_path: str) -> tuple[Path, str]:
    """解析虚拟路径的父目录（真实路径），返回（父目录, 条目名）。

    父目录必须存在；条目名不能为空或根。
    """
    normalized: str = validate_relative_path(virtual_path)
    if normalized == "/":
        raise InvalidPathError("不能对根目录执行该操作")

    parent_virtual: str = posixpath.dirname(normalized)
    entry_name: str = posixpath.basename(normalized)
    if not entry_name or entry_name in (".", ".."):
        raise InvalidPathError("路径缺少有效的条目名称")

    parent_path: Path = resolve_path(parent_virtual, follow_link=True)
    if not os.path.isdir(parent_path):
        raise NotFoundError(f"父目录不存在: {parent_virtual}")
    return parent_path, entry_name


def _ensure_target_absent(target: Path, overwrite: bool) -> None:
    """检查目标不存在，或按 overwrite 决定是否允许覆盖。"""
    if not os.path.lexists(target):
        return
    if not overwrite:
        raise ConflictError(f"目标已存在: {target.name}")
    if os.path.isdir(target) and not os.path.islink(target):
        raise ConflictError("目标已存在且为目录，不允许覆盖")


def create_file(virtual_path: str) -> FsEntry:
    """创建空文件，返回新条目元数据。"""
    parent_path, entry_name = _resolve_parent(virtual_path)
    target: Path = parent_path / entry_name
    _ensure_target_absent(target, overwrite=False)

    try:
        with open(target, "x"):
            pass
    except FileExistsError as exc:
        raise ConflictError("目标文件已存在") from exc
    except PermissionError as exc:
        raise ForbiddenError("没有权限创建文件") from exc

    return build_entry(target, validate_relative_path(virtual_path), follow_link=False)


def create_directory(virtual_path: str) -> FsEntry:
    """创建文件夹，返回新条目元数据。"""
    parent_path, entry_name = _resolve_parent(virtual_path)
    target: Path = parent_path / entry_name
    _ensure_target_absent(target, overwrite=False)

    try:
        os.mkdir(target)
    except FileExistsError as exc:
        raise ConflictError("目标文件夹已存在") from exc
    except PermissionError as exc:
        raise ForbiddenError("没有权限创建文件夹") from exc

    return build_entry(target, validate_relative_path(virtual_path), follow_link=False)


def create_symbolic_link(virtual_path: str, link_target: str) -> FsEntry:
    """创建符号链接，返回新条目元数据。"""
    parent_path, entry_name = _resolve_parent(virtual_path)
    target: Path = parent_path / entry_name
    _ensure_target_absent(target, overwrite=False)

    if not link_target or "\x00" in link_target:
        raise InvalidPathError("链接目标不能为空")

    try:
        os.symlink(link_target, target)
    except FileExistsError as exc:
        raise ConflictError("目标链接已存在") from exc
    except PermissionError as exc:
        raise ForbiddenError("没有权限创建符号链接") from exc

    return build_entry(target, validate_relative_path(virtual_path), follow_link=False)


def delete_path(virtual_path: str, recursive: bool, follow_link: bool) -> None:
    """删除文件或文件夹；文件夹非空且非递归删除时拒绝。"""
    normalized: str = validate_relative_path(virtual_path)
    if normalized == "/":
        raise InvalidPathError("不能删除根目录")

    target: Path = resolve_path(normalized, follow_link=follow_link)
    if not os.path.lexists(target):
        raise NotFoundError(f"路径不存在: {normalized}")

    is_link: bool = os.path.islink(target)
    is_directory: bool = os.path.isdir(target) and not is_link

    if is_link:
        os.unlink(target)
        return

    if is_directory:
        if not recursive and any(True for _ in os.scandir(target)):
            raise ConflictError("文件夹非空，拒绝删除")
        if recursive:
            shutil.rmtree(target)
        else:
            os.rmdir(target)
        return

    os.remove(target)


def _rename_target(
    target: Path, normalized: str, new_name: Optional[str]
) -> tuple[Path, str]:
    """重命名当前条目，返回（新路径, 新虚拟路径）。"""
    if new_name is None or new_name == "":
        return target, normalized
    if "/" in new_name or "\x00" in new_name or new_name in (".", ".."):
        raise InvalidPathError("非法的条目名称")

    new_target: Path = target.parent / new_name
    if os.path.lexists(new_target):
        raise ConflictError("目标名称已存在")
    shutil.move(target, new_target)
    new_normalized: str = posixpath.join(posixpath.dirname(normalized), new_name)
    return new_target, new_normalized


def _move_target(
    target: Path, normalized: str, new_virtual_path: str
) -> tuple[Path, str]:
    """移动条目到新的虚拟路径（移动+重命名），返回（新路径, 新虚拟路径）。"""
    new_normalized: str = validate_relative_path(new_virtual_path)
    if new_normalized == "/":
        raise InvalidPathError("不能移动到根目录")

    parent_path, entry_name = _resolve_parent(new_normalized)
    new_target: Path = parent_path / entry_name
    if os.path.lexists(new_target):
        raise ConflictError("目标路径已存在")
    shutil.move(target, new_target)
    return new_target, new_normalized


def _apply_hidden_flag(target: Path, normalized: str, is_hidden: bool) -> tuple[Path, str]:
    """根据隐藏标记调整名称（Linux 约定：名称以点开头为隐藏）。"""
    current_hidden: bool = target.name.startswith(".")
    if current_hidden == is_hidden:
        return target, normalized

    if is_hidden:
        new_name: str = "." + target.name
    else:
        new_name: str = target.name.lstrip(".")
        if not new_name:
            raise InvalidPathError("无法修改该条目的隐藏状态")

    new_target: Path = target.parent / new_name
    if os.path.lexists(new_target):
        raise ConflictError("目标名称已存在")
    shutil.move(target, new_target)
    new_normalized: str = posixpath.join(posixpath.dirname(normalized), new_name)
    return new_target, new_normalized


def update_metadata(
    virtual_path: str,
    follow_link: bool,
    *,
    new_name: Optional[str] = None,
    new_path: Optional[str] = None,
    modified_at: Optional[float] = None,
    accessed_at: Optional[float] = None,
    permissions: Optional[str] = None,
    is_hidden: Optional[bool] = None,
) -> FsEntry:
    """修改条目元数据：重命名、移动、时间、权限、隐藏标记。"""
    normalized: str = validate_relative_path(virtual_path)
    target: Path = resolve_path(normalized, follow_link=follow_link)
    if not os.path.lexists(target):
        raise NotFoundError(f"路径不存在: {normalized}")

    # 名称与绝对路径同时给出时，名称参数无效
    if new_path is not None:
        target, normalized = _move_target(target, normalized, new_path)
    elif new_name is not None:
        target, normalized = _rename_target(target, normalized, new_name)

    if is_hidden is not None:
        target, normalized = _apply_hidden_flag(target, normalized, is_hidden)

    if modified_at is not None or accessed_at is not None:
        _apply_timestamps(target, modified_at, accessed_at, follow_link=follow_link)

    if permissions is not None:
        try:
            if os.path.islink(target):
                os.lchmod(target, permissions_to_mode(permissions))
            else:
                apply_permissions(str(target), permissions)
        except PermissionError as exc:
            raise ForbiddenError("没有权限修改权限属性") from exc

    return build_entry(target, normalized, follow_link=follow_link)


def _apply_timestamps(
    target: Path,
    modified_at: Optional[float],
    accessed_at: Optional[float],
    *,
    follow_link: bool,
) -> None:
    """更新访问/修改时间，未提供的字段保持原值。"""
    file_stat = target.stat()
    new_accessed: float = accessed_at if accessed_at is not None else file_stat.st_atime
    new_modified: float = modified_at if modified_at is not None else file_stat.st_mtime
    os.utime(
        target,
        (new_accessed, new_modified),
        follow_symlinks=not follow_link,
    )


def upload_small_file(
    directory_virtual: str,
    filename: str,
    content_stream,
    overwrite: bool,
) -> FsEntry:
    """将小文件写入目录，先写临时文件再原子重命名。"""
    safe_name: str = os.path.basename(filename)
    if not safe_name or safe_name in (".", ".."):
        raise InvalidPathError("非法的文件名")

    normalized_dir: str = validate_relative_path(directory_virtual)
    parent_path: Path = resolve_path(normalized_dir, follow_link=True)
    if not os.path.isdir(parent_path):
        raise NotFoundError(f"目录不存在: {directory_virtual}")

    target_path: Path = parent_path / safe_name
    if os.path.lexists(target_path):
        if not overwrite:
            raise ConflictError("目标文件已存在")
        if os.path.isdir(target_path):
            raise ConflictError("目标已存在且为目录")

    temp_path: Path = parent_path / f".{safe_name}.upload-{uuid.uuid4().hex}.tmp"
    try:
        with open(temp_path, "wb") as output_handle:
            while True:
                block: bytes = content_stream.read(_UPLOAD_BUFFER_SIZE)
                if not block:
                    break
                output_handle.write(block)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temp_path, target_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    virtual_target: str = (
        "/" + safe_name if normalized_dir == "/" else normalized_dir.rstrip("/") + "/" + safe_name
    )
    return build_entry(target_path, virtual_target, follow_link=False)


def copy_path(
    source_virtual: str, destination_virtual: str, overwrite: bool
) -> FsEntry:
    """复制文件或文件夹（递归）到目标位置，返回副本元数据。"""
    source_normalized: str = validate_relative_path(source_virtual)
    source_path: Path = resolve_path(source_normalized, follow_link=True)
    if not os.path.lexists(source_path):
        raise NotFoundError(f"源路径不存在: {source_normalized}")

    dest_parent, dest_name = _resolve_parent(destination_virtual)
    dest_path: Path = dest_parent / dest_name

    try:
        if os.path.isdir(source_path) and not os.path.islink(source_path):
            if os.path.lexists(dest_path):
                if not overwrite:
                    raise ConflictError("目标已存在")
                if os.path.isdir(dest_path) and not os.path.islink(dest_path):
                    shutil.copytree(source_path, dest_path, symlinks=True, dirs_exist_ok=True)
                else:
                    raise ConflictError("目标已存在且不是目录，无法合并复制")
            else:
                shutil.copytree(source_path, dest_path, symlinks=True)
        else:
            if os.path.lexists(dest_path):
                if not overwrite:
                    raise ConflictError("目标已存在")
                os.remove(dest_path)
            shutil.copy2(source_path, dest_path)
    except PermissionError as exc:
        raise ForbiddenError("没有权限执行复制") from exc

    return build_entry(dest_path, validate_relative_path(destination_virtual), follow_link=False)
