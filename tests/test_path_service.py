"""PathService 单元测试。

覆盖虚拟路径规范化、真实路径解析、沙箱边界校验、虚拟路径反向
转换以及父目录存在性校验。符号链接相关用例在 Windows 上默认
跳过，因为创建符号链接需要管理员权限或开启开发者模式。
"""

import sys
from pathlib import Path

import pytest

from app.config import Config
from app.errors import BusinessError, ErrorCode
from app.services.path_service import PathService


SYMLINK_SKIP_REASON = "Windows 创建符号链接需要管理员权限或开发者模式"
"""符号链接用例在 Windows 上跳过的原因说明。"""


def build_service(sandbox: Path) -> PathService:
    """构造使用指定沙箱根目录的 :class:`PathService`。

    Args:
        sandbox: 用作沙箱根目录的临时路径。

    Returns:
        配置好的路径服务实例。
    """
    config = Config(sandbox_root=sandbox)
    return PathService(config)


def test_normalize_root_paths(tmp_path: Path) -> None:
    """根路径的各种输入形式都应规范化为 ``/``。"""
    service = build_service(tmp_path)
    assert service.normalize(None) == "/"
    assert service.normalize("") == "/"
    assert service.normalize("   ") == "/"
    assert service.normalize("/") == "/"
    assert service.normalize("///") == "/"


def test_normalize_simple_paths(tmp_path: Path) -> None:
    """常规路径应被折叠多余分隔符与当前目录段。"""
    service = build_service(tmp_path)
    assert service.normalize("foo/bar") == "/foo/bar"
    assert service.normalize("/foo/bar") == "/foo/bar"
    assert service.normalize("/foo//bar") == "/foo/bar"
    assert service.normalize("/foo/./bar") == "/foo/bar"
    assert service.normalize("/foo/bar/") == "/foo/bar"


def test_normalize_rejects_parent_reference(tmp_path: Path) -> None:
    """包含 ``..`` 段的路径应被拒绝。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.normalize("/foo/../bar")
    assert exc_info.value.code == ErrorCode.INVALID_PATH


def test_normalize_rejects_home_reference(tmp_path: Path) -> None:
    """包含独立 ``~`` 段的路径应被拒绝。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.normalize("~")
    assert exc_info.value.code == ErrorCode.INVALID_PATH

    with pytest.raises(BusinessError) as exc_info:
        service.normalize("/~/foo")
    assert exc_info.value.code == ErrorCode.INVALID_PATH


def test_normalize_allows_tilde_inside_segment(tmp_path: Path) -> None:
    """段内包含 ``~`` 但段本身不等于 ``~`` 时应被允许。"""
    service = build_service(tmp_path)
    assert service.normalize("/foo~bar") == "/foo~bar"
    assert service.normalize("/~foo") == "/~foo"


def test_resolve_real_path_simple(tmp_path: Path) -> None:
    """普通存在的文件应解析为对应的真实路径。"""
    service = build_service(tmp_path)
    (tmp_path / "foo").mkdir()
    (tmp_path / "foo" / "bar.txt").write_text("hello", encoding="utf-8")

    real_path = service.resolve_real_path("/foo/bar.txt")
    assert real_path == (tmp_path / "foo" / "bar.txt").resolve()


def test_resolve_real_path_root(tmp_path: Path) -> None:
    """根路径应解析为沙箱根目录。"""
    service = build_service(tmp_path)
    assert service.resolve_real_path("/") == tmp_path.resolve()
    assert service.resolve_real_path(None) == tmp_path.resolve()


def test_resolve_real_path_nonexistent(tmp_path: Path) -> None:
    """不存在的路径也应解析成功，供调用方后续处理。"""
    service = build_service(tmp_path)
    real_path = service.resolve_real_path("/foo/bar.txt")
    assert real_path == (tmp_path / "foo" / "bar.txt").resolve()


def test_resolve_real_path_rejects_invalid_virtual_path(
    tmp_path: Path,
) -> None:
    """虚拟路径非法时解析应抛出 ``INVALID_PATH``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.resolve_real_path("/foo/../etc/passwd")
    assert exc_info.value.code == ErrorCode.INVALID_PATH


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_resolve_real_path_rejects_symlink_escape(tmp_path: Path) -> None:
    """符号链接指向沙箱外时，跟随解析应抛出 ``PATH_OUTSIDE_SANDBOX``。"""
    outside = tmp_path / "outside_sandbox"
    outside.mkdir()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    service = build_service(sandbox)

    escape_link = sandbox / "escape"
    escape_link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(BusinessError) as exc_info:
        service.resolve_real_path("/escape/secret.txt", follow_link=True)
    assert exc_info.value.code == ErrorCode.PATH_OUTSIDE_SANDBOX


@pytest.mark.skipif(sys.platform == "win32", reason=SYMLINK_SKIP_REASON)
def test_resolve_real_path_does_not_follow_link_when_disabled(
    tmp_path: Path,
) -> None:
    """``follow_link=False`` 时最终段应保留为符号链接本身。"""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    service = build_service(sandbox)

    target = sandbox / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = sandbox / "link"
    link.symlink_to(target)

    real_path = service.resolve_real_path("/link", follow_link=False)
    assert real_path == link
    assert real_path.is_symlink()


def test_to_virtual_path(tmp_path: Path) -> None:
    """真实路径应被转换为对应的沙箱虚拟路径。"""
    service = build_service(tmp_path)
    assert service.to_virtual_path(tmp_path) == "/"
    assert service.to_virtual_path(tmp_path / "foo") == "/foo"
    assert (
        service.to_virtual_path(tmp_path / "foo" / "bar.txt")
        == "/foo/bar.txt"
    )


def test_to_virtual_path_rejects_outside_sandbox(tmp_path: Path) -> None:
    """沙箱外的真实路径应抛出 ``PATH_OUTSIDE_SANDBOX``。"""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    service = build_service(sandbox)

    with pytest.raises(BusinessError) as exc_info:
        service.to_virtual_path(outside)
    assert exc_info.value.code == ErrorCode.PATH_OUTSIDE_SANDBOX


def test_ensure_parent_exists_ok(tmp_path: Path) -> None:
    """父目录存在时不应抛出异常。"""
    service = build_service(tmp_path)
    (tmp_path / "foo").mkdir()
    service.ensure_parent_exists(tmp_path / "foo" / "bar.txt")


def test_ensure_parent_exists_raises_when_missing(tmp_path: Path) -> None:
    """父目录不存在时应抛出 ``PARENT_NOT_FOUND``。"""
    service = build_service(tmp_path)
    with pytest.raises(BusinessError) as exc_info:
        service.ensure_parent_exists(tmp_path / "nonexistent" / "bar.txt")
    assert exc_info.value.code == ErrorCode.PARENT_NOT_FOUND
