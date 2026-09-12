"""路径相关默认常量。"""

# 沙箱根目录默认值，可通过环境变量 SANDBOX_ROOT 或 .env 覆盖
DEFAULT_SANDBOX_ROOT: str = "./sandbox"

# 前端静态资源根目录，相对于项目根目录
STATIC_DIR: str = "./static"

# 前端 HTML 入口文件名
INDEX_HTML_FILENAME: str = "index.html"

# 上传临时根目录默认值，可通过环境变量 UPLOAD_TEMP_ROOT 覆盖
# 必须位于沙箱之外，且不能被 /files 或 /static 接口访问
DEFAULT_UPLOAD_TEMP_ROOT: str = "./.file-explorer-temp"
