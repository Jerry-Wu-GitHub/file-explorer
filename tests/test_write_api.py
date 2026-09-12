"""写操作 API 集成测试。

覆盖 ``POST /files``、``POST /folders``、``DELETE /files``、
``PATCH /files`` 与 ``POST /files/copy`` 的成功与失败路径，并
验证统一响应格式。
"""

import sys
from functools import partial
from pathlib import Path
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Config
from app.dependencies.services import get_modify_service, get_write_service
from app.errors import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routes.files import router as files_router
from app.routes.folders import router as folders_router
from app.services.metadata_service import MetadataService
from app.services.modify_service import ModifyService
from app.services.path_service import PathService
from app.services.write_service import WriteService


FILES_PREFIX = "/api/v1/files"
"""测试用文件接口前缀。"""

FOLDERS_PREFIX = "/api/v1/folders"
"""测试用文件夹接口前缀。"""

CHMOD_SKIP_REASON = "Windows 的 chmod 不支持完整权限位"
"""权限位相关用例在 Windows 上跳过的原因说明。"""


def return_constant(value):
    """返回固定实例，配合 :func:`functools.partial` 用作依赖替换。"""
    return value


def build_client(sandbox: Path) -> TestClient:
    """构造使用指定沙箱根目录的测试客户端。"""
    config = Config(sandbox_root=sandbox)
    path_service = PathService(config)
    metadata_service = MetadataService(path_service)
    write_service = WriteService(path_service, metadata_service)
    modify_service = ModifyService(path_service, metadata_service)

    application = FastAPI()
    register_exception_handlers(application)
    application.add_middleware(RequestIdMiddleware)
    application.include_router(files_router, prefix=FILES_PREFIX)
    application.include_router(folders_router, prefix=FOLDERS_PREFIX)
    application.dependency_overrides[get_write_service] = partial(
        return_constant, write_service
    )
    application.dependency_overrides[get_modify_service] = partial(
        return_constant, modify_service
    )
    return TestClient(application, raise_server_exceptions=False)


def test_create_file_success(tmp_path: Path) -> None:
    """创建文件应返回 201 与文件元数据。"""
    client = build_client(tmp_path)
    response = client.post(f"{FILES_PREFIX}", json={"path": "/notes.txt"})
    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["name"] == "notes.txt"
    assert payload["path"] == "/notes.txt"
    assert payload["type"] == "file"
    assert payload["isHidden"] is False


def test_create_file_rejects_missing_parent(tmp_path: Path) -> None:
    """父目录不存在时返回 ``PARENT_NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.post(f"{FILES_PREFIX}", json={"path": "/missing/x.txt"})
    assert response.status_code == 404
    assert response.json()["code"] == "PARENT_NOT_FOUND"


def test_create_file_rejects_existing(tmp_path: Path) -> None:
    """目标已存在时返回 ``FILE_EXISTS``。"""
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(f"{FILES_PREFIX}", json={"path": "/notes.txt"})
    assert response.status_code == 409
    assert response.json()["code"] == "FILE_EXISTS"


def test_create_file_rejects_invalid_path(tmp_path: Path) -> None:
    """路径含 ``..`` 时返回 ``INVALID_PATH``。"""
    client = build_client(tmp_path)
    response = client.post(f"{FILES_PREFIX}", json={"path": "/../evil.txt"})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PATH"


def test_create_folder_success(tmp_path: Path) -> None:
    """创建文件夹应返回 201 与目录元数据。"""
    client = build_client(tmp_path)
    response = client.post(f"{FOLDERS_PREFIX}", json={"path": "/docs"})
    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["type"] == "directory"
    assert payload["mimeType"] is None


def test_create_folder_rejects_existing(tmp_path: Path) -> None:
    """已存在的目录返回 ``FILE_EXISTS``。"""
    (tmp_path / "docs").mkdir()
    client = build_client(tmp_path)
    response = client.post(f"{FOLDERS_PREFIX}", json={"path": "/docs"})
    assert response.status_code == 409
    assert response.json()["code"] == "FILE_EXISTS"


def test_delete_file_success(tmp_path: Path) -> None:
    """删除文件应返回 204，无响应体。"""
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.delete(FILES_PREFIX, params={"path": "/notes.txt"})
    assert response.status_code == 204
    assert response.content == b""
    assert not (tmp_path / "notes.txt").exists()


def test_delete_directory_recursive(tmp_path: Path) -> None:
    """递归删除非空目录应成功。"""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.txt").write_text("", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.delete(
        FILES_PREFIX, params={"path": "/sub", "recursive": True}
    )
    assert response.status_code == 204
    assert not (tmp_path / "sub").exists()


def test_delete_directory_without_recursive_returns_conflict(
    tmp_path: Path,
) -> None:
    """目录非空且未递归删除时返回 ``DIRECTORY_NOT_EMPTY``。"""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.txt").write_text("", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.delete(FILES_PREFIX, params={"path": "/sub"})
    assert response.status_code == 409
    assert response.json()["code"] == "DIRECTORY_NOT_EMPTY"


def test_delete_nonexistent_returns_404(tmp_path: Path) -> None:
    """删除不存在的路径返回 ``NOT_FOUND``。"""
    client = build_client(tmp_path)
    response = client.delete(FILES_PREFIX, params={"path": "/missing"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_update_metadata_rename(tmp_path: Path) -> None:
    """只修改名称应生效。"""
    (tmp_path / "old.txt").write_text("hello", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.patch(
        FILES_PREFIX,
        params={"path": "/old.txt"},
        json={"name": "new.txt"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["name"] == "new.txt"
    assert payload["path"] == "/new.txt"
    assert (tmp_path / "new.txt").is_file()


@pytest.mark.skipif(sys.platform == "win32", reason=CHMOD_SKIP_REASON)
def test_update_metadata_modify_permissions(tmp_path: Path) -> None:
    """修改权限应反映在返回的元数据中。"""
    file_path = tmp_path / "file.txt"
    file_path.write_text("", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.patch(
        FILES_PREFIX,
        params={"path": "/file.txt"},
        json={"permissions": "rwxr-xr-x"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["permissions"] == "rwxr-xr-x"


def test_update_metadata_rejects_invalid_permissions(
    tmp_path: Path,
) -> None:
    """非法权限字符串返回 ``VALIDATION_ERROR``。"""
    (tmp_path / "file.txt").write_text("", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.patch(
        FILES_PREFIX,
        params={"path": "/file.txt"},
        json={"permissions": "rwx"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_update_metadata_toggle_hidden(tmp_path: Path) -> None:
    """切换隐藏属性应反映在文件名与 ``isHidden``。"""
    (tmp_path / "file.txt").write_text("", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.patch(
        FILES_PREFIX,
        params={"path": "/file.txt"},
        json={"isHidden": True},
    )
    payload = response.json()["data"]
    assert payload["name"] == ".file.txt"
    assert payload["isHidden"] is True


def test_copy_file_success(tmp_path: Path) -> None:
    """复制文件应返回 201 与副本元数据。"""
    (tmp_path / "source.txt").write_text("hello", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(
        f"{FILES_PREFIX}/copy",
        json={"source": "/source.txt", "destination": "/copy.txt"},
    )
    assert response.status_code == 201
    assert response.json()["data"]["path"] == "/copy.txt"
    assert (tmp_path / "copy.txt").is_file()


def test_copy_directory_success(tmp_path: Path) -> None:
    """递归复制文件夹应成功。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.txt").write_text("a", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(
        f"{FILES_PREFIX}/copy",
        json={"source": "/src", "destination": "/dst"},
    )
    assert response.status_code == 201
    assert (tmp_path / "dst" / "a.txt").is_file()


def test_copy_rejects_existing_target(tmp_path: Path) -> None:
    """目标存在且不允许覆盖时返回 ``FILE_EXISTS``。"""
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(
        f"{FILES_PREFIX}/copy",
        json={
            "source": "/a.txt",
            "destination": "/b.txt",
            "overwrite": False,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "FILE_EXISTS"


def test_copy_overwrites_when_allowed(tmp_path: Path) -> None:
    """``overwrite=true`` 时覆盖目标文件。"""
    (tmp_path / "a.txt").write_text("new", encoding="utf-8")
    (tmp_path / "b.txt").write_text("old", encoding="utf-8")
    client = build_client(tmp_path)
    response = client.post(
        f"{FILES_PREFIX}/copy",
        json={
            "source": "/a.txt",
            "destination": "/b.txt",
            "overwrite": True,
        },
    )
    assert response.status_code == 201
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "new"
