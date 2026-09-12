"""沙箱路径解析服务。

本模块提供 :class:`PathService`，负责将用户输入的虚拟路径解析为
沙箱内的真实路径，并确保最终真实路径依然位于沙箱根目录内。所有
文件系统相关的 API 必须先经过该服务进行路径解析与校验，禁止直接
拼接用户输入的路径。
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from ..config import Config, get_config
from ..errors import BusinessError, ErrorCode
from ..utils.path_utils import normalize_virtual_path


class PathService:
    """负责在沙箱内解析与校验虚拟路径的服务。

    Attributes:
        sandbox_root: 沙箱根目录的真实绝对路径。
    """

    def __init__(self, config: Config) -> None:
        """构造路径服务。

        Args:
            config: 项目全局配置。
        """
        self._config: Config = config
        self._sandbox_root: Path = config.sandbox_root.resolve()

    @property
    def sandbox_root(self) -> Path:
        """返回沙箱根目录的真实绝对路径。

        Returns:
            沙箱根目录的 :class:`Path` 对象。
        """
        return self._sandbox_root

    def normalize(self, virtual_path: Optional[str]) -> str:
        """将输入路径规范化为沙箱内的绝对虚拟路径。

        Args:
            virtual_path: 用户输入的虚拟路径，可为 ``None``。

        Returns:
            以 ``/`` 开头的规范化虚拟路径。

        Raises:
            BusinessError: 路径非法。
        """
        return normalize_virtual_path(virtual_path)

    def resolve_real_path(
        self,
        virtual_path: Optional[str],
        follow_link: bool = True,
    ) -> Path:
        """将虚拟路径解析为真实路径，并校验其位于沙箱内。

        当 ``follow_link`` 为 ``True`` 时，最终段若为符号链接会被
        跟随，解析结果指向链接目标；当为 ``False`` 时，仅解析父目录，
        最终段以符号链接自身形式保留，便于以 ``link`` 类型返回。

        Args:
            virtual_path: 用户输入的虚拟路径，可为 ``None``。
            follow_link: 是否跟随最终段的符号链接。

        Returns:
            解析后的真实绝对路径。

        Raises:
            BusinessError: 路径非法或解析后越出沙箱根目录。
        """
        normalized = self.normalize(virtual_path)
        relative = normalized.lstrip("/")
        base = self._sandbox_root

        if relative == "":
            real_path = base
        elif follow_link:
            real_path = (base / relative).resolve()
        else:
            real_path = self._resolve_without_following_final_link(
                base, relative
            )

        self.ensure_inside_sandbox(real_path)
        return real_path

    def ensure_inside_sandbox(self, real_path: Path) -> None:
        """校验真实路径位于沙箱根目录内。

        Args:
            real_path: 待校验的真实路径。

        Raises:
            BusinessError: 路径越出沙箱根目录。
        """
        try:
            real_path.relative_to(self._sandbox_root)
        except ValueError as exc:
            raise BusinessError(
                ErrorCode.PATH_OUTSIDE_SANDBOX,
                f"真实路径超出沙箱根目录：{real_path}",
            ) from exc

    def to_virtual_path(self, real_path: Path) -> str:
        """将真实路径转换为沙箱内的虚拟路径。

        不对输入路径做 ``resolve``，以保留符号链接最终段的原貌。
        若调用方传入的路径在结构上越出沙箱根目录，则抛出
        ``PATH_OUTSIDE_SANDBOX``。安全性由
        :meth:`resolve_real_path` 保证：所有对外暴露的路径都必须
        先经其校验。

        Args:
            real_path: 位于沙箱内的真实路径。

        Returns:
            以 ``/`` 开头的虚拟路径。

        Raises:
            BusinessError: 路径越出沙箱根目录。
        """
        try:
            relative = real_path.relative_to(self._sandbox_root)
        except ValueError as exc:
            raise BusinessError(
                ErrorCode.PATH_OUTSIDE_SANDBOX,
                f"真实路径超出沙箱根目录：{real_path}",
            ) from exc
        relative_string = str(relative).replace("\\", "/")
        if relative_string == ".":
            return "/"
        return "/" + relative_string

    def ensure_parent_exists(self, real_path: Path) -> None:
        """校验真实路径的父目录存在且为目录。

        Args:
            real_path: 目标真实路径。

        Raises:
            BusinessError: 父目录不存在或不是目录。
        """
        parent = real_path.parent
        if not parent.exists() or not parent.is_dir():
            raise BusinessError(
                ErrorCode.PARENT_NOT_FOUND,
                f"父目录不存在：{parent}",
            )

    def _resolve_without_following_final_link(
        self,
        base: Path,
        relative: str,
    ) -> Path:
        """解析路径但不跟随最终段的符号链接。

        仅对父目录部分执行 ``resolve``，最终段原样拼接到解析后的
        父目录上，从而保留最终段本身的符号链接语义。

        Args:
            base: 沙箱根目录。
            relative: 相对于沙箱根目录的路径字符串。

        Returns:
            解析后的路径，最终段保留原样。
        """
        if "/" not in relative:
            return base / relative
        parent_virtual, name = relative.rsplit("/", 1)
        parent_real = (base / parent_virtual).resolve()
        return parent_real / name


@lru_cache(maxsize=1)
def get_path_service() -> PathService:
    """获取默认的 :class:`PathService` 单例。

    使用 :func:`app.config.get_config` 返回的全局配置构造路径服务，
    并通过 :func:`functools.lru_cache` 保证进程内单例。

    Returns:
        路径服务实例。
    """
    return PathService(get_config())


__all__ = ["PathService", "get_path_service"]
