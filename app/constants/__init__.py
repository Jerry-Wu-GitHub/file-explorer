"""项目默认常量集合。

所有变量名大写；其中部分变量可通过环境变量或 .env 覆盖（具体覆盖逻辑见 app/config.py）。
"""

from . import pagination, paths, uploads

__all__ = ["pagination", "paths", "uploads"]
