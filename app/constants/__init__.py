"""项目全局常量包。

本包统一汇总并重新导出 :mod:`app.constants` 下各子模块中定义的
常量，使外部可以通过 ``from app.constants import XXX`` 的方式引用，
而不必关心常量所在的具体子模块。

子模块划分：

- :mod:`app.constants.server`：服务器运行相关常量。
- :mod:`app.constants.filesystem`：文件系统业务相关常量。
- :mod:`app.constants.upload`：分片上传相关常量。
- :mod:`app.constants.frontend`：前端资源与主题相关常量。
"""

from app.constants.frontend import *  # noqa: F401,F403
from app.constants.filesystem import *  # noqa: F401,F403
from app.constants.server import *  # noqa: F401,F403
from app.constants.upload import *  # noqa: F401,F403
