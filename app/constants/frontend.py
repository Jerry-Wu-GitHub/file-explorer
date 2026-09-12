"""前端相关的常量定义。

本模块定义前端静态资源目录、页面文件名、主题、强调色，
以及浏览器本地存储键名等常量。
"""

STATIC_DIRECTORY: str = "./static"
"""前端静态资源根目录。"""

STATIC_HTML_DIRECTORY: str = "html"
"""前端 HTML 页面子目录名。"""

STATIC_CSS_DIRECTORY: str = "css"
"""前端 CSS 子目录名。"""

STATIC_JS_DIRECTORY: str = "js"
"""前端 JavaScript 子目录名。"""

INDEX_PAGE_FILENAME: str = "index.html"
"""主页 HTML 文件名。"""

METADATA_PAGE_FILENAME: str = "metadata.html"
"""属性页 HTML 文件名。"""

INDEX_PAGE_ROUTE: str = "/"
"""主页路由路径。"""

METADATA_PAGE_ROUTE: str = "/metadata"
"""属性页路由路径。"""

THEME_LIGHT: str = "light"
"""亮色主题标识。"""

THEME_DARK: str = "dark"
"""暗色主题标识。"""

THEME_SYSTEM: str = "system"
"""跟随系统主题标识。"""

DEFAULT_THEME: str = THEME_SYSTEM
"""默认主题，默认为跟随系统。"""

SUPPORTED_THEMES: tuple[str, ...] = (THEME_LIGHT, THEME_DARK, THEME_SYSTEM)
"""支持的主题集合。"""

DEFAULT_ACCENT_COLOR: str = "#33ff66"
"""默认强调色，控制台绿色。"""

STORAGE_KEY_THEME: str = "fe.theme"
"""浏览器本地存储中保存主题的键名。"""

STORAGE_KEY_ACCENT_COLOR: str = "fe.accentColor"
"""浏览器本地存储中保存强调色的键名。"""

STORAGE_KEY_RECENT_FOLDER: str = "fe.recentFolder"
"""浏览器本地存储中保存最近访问文件夹路径的键名。"""

STORAGE_KEY_NAVIGATION_HISTORY: str = "fe.navigationHistory"
"""浏览器本地存储中保存导航历史的键名。"""

DEFAULT_SEARCH_DEBOUNCE_MILLISECONDS: int = 300
"""搜索输入框默认防抖时间（毫秒）。"""

DEFAULT_LIST_VIEW_MODE: str = "grid"
"""文件列表默认视图模式，可选 ``grid``、``list``。"""

__all__ = [
    "STATIC_DIRECTORY",
    "STATIC_HTML_DIRECTORY",
    "STATIC_CSS_DIRECTORY",
    "STATIC_JS_DIRECTORY",
    "INDEX_PAGE_FILENAME",
    "METADATA_PAGE_FILENAME",
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
