"""前端相关的常量定义。

本模块定义前端静态资源目录、页面文件名、主题、强调色，
以及浏览器本地存储键名等常量。
"""

from pathlib import Path

# 项目根目录
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

# 前端静态资源根目录
STATIC_DIRECTORY: Path = BASE_DIR / "static"

# 前端 HTML 页面子目录
STATIC_HTML_DIRECTORY_NAME = "html"
STATIC_HTML_DIRECTORY: Path = STATIC_DIRECTORY / STATIC_HTML_DIRECTORY_NAME

# 前端 CSS 子目录
STATIC_CSS_DIRECTORY_NAME = "css"
STATIC_CSS_DIRECTORY: Path = STATIC_DIRECTORY / STATIC_CSS_DIRECTORY_NAME

# 前端 JavaScript 子目录
STATIC_JS_DIRECTORY_NAME = "js"
STATIC_JS_DIRECTORY: Path = STATIC_DIRECTORY / STATIC_JS_DIRECTORY_NAME

# 主页 HTML 文件名
INDEX_PAGE_FILENAME: str = "index.html"

# 主页 HTML 文件路径
INDEX_PAGE_PATH: Path = STATIC_HTML_DIRECTORY / INDEX_PAGE_FILENAME

# 属性页 HTML 文件名
METADATA_PAGE_FILENAME: str = "metadata.html"

# 属性页 HTML 文件路径
METADATA_PAGE_PATH: Path = STATIC_HTML_DIRECTORY / METADATA_PAGE_FILENAME

# 主页路由路径
INDEX_PAGE_ROUTE: str = "/"

# 属性页路由路径
METADATA_PAGE_ROUTE: str = "/metadata"

# 亮色主题标识
THEME_LIGHT: str = "light"

# 暗色主题标识
THEME_DARK: str = "dark"

# 跟随系统主题标识
THEME_SYSTEM: str = "system"

# 默认主题，默认为跟随系统
DEFAULT_THEME: str = THEME_SYSTEM

# 支持的主题集合
SUPPORTED_THEMES: tuple[str, ...] = (THEME_LIGHT, THEME_DARK, THEME_SYSTEM)

# 默认强调色，控制台绿色
DEFAULT_ACCENT_COLOR: str = "#33ff66"

# 浏览器本地存储中保存主题的键名
STORAGE_KEY_THEME: str = "fe.theme"

# 浏览器本地存储中保存强调色的键名
STORAGE_KEY_ACCENT_COLOR: str = "fe.accentColor"

# 浏览器本地存储中保存最近访问文件夹路径的键名
STORAGE_KEY_RECENT_FOLDER: str = "fe.recentFolder"

# 浏览器本地存储中保存导航历史的键名
STORAGE_KEY_NAVIGATION_HISTORY: str = "fe.navigationHistory"

# 搜索输入框默认防抖时间（毫秒）
DEFAULT_SEARCH_DEBOUNCE_MILLISECONDS: int = 300

# 文件列表默认视图模式，可选 ``grid``、``list``
DEFAULT_LIST_VIEW_MODE: str = "grid"

__all__ = [
    "BASE_DIR",
    "STATIC_DIRECTORY",
    "STATIC_HTML_DIRECTORY_NAME",
    "STATIC_HTML_DIRECTORY",
    "STATIC_CSS_DIRECTORY_NAME",
    "STATIC_CSS_DIRECTORY",
    "STATIC_JS_DIRECTORY_NAME",
    "STATIC_JS_DIRECTORY",
    "INDEX_PAGE_FILENAME",
    "INDEX_PAGE_PATH",
    "METADATA_PAGE_FILENAME",
    "METADATA_PAGE_PATH",
    "INDEX_PAGE_ROUTE",
    "METADATA_PAGE_ROUTE",
    "THEME_LIGHT",
    "THEME_DARK",
    "THEME_SYSTEM",
    "DEFAULT_THEME",
    "SUPPORTED_THEMES",
    "DEFAULT_ACCENT_COLOR",
    "STORAGE_KEY_THEME",
    "STORAGE_KEY_ACCENT_COLOR",
    "STORAGE_KEY_RECENT_FOLDER",
    "STORAGE_KEY_NAVIGATION_HISTORY",
    "DEFAULT_SEARCH_DEBOUNCE_MILLISECONDS",
    "DEFAULT_LIST_VIEW_MODE",
]
