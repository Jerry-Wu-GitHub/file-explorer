/**
 * 前端全局常量与本地存储键。
 *
 * 集中定义接口前缀、分页默认值、主题常量、本地存储键名等，
 * 避免在其他模块中散落魔法值。
 */

/** 后端业务 API 的公共前缀。 */
export const API_PREFIX = "/api/v1";

/** 前端静态资源前缀。 */
export const STATIC_PREFIX = "/static";

/** 主题取值：亮色。 */
export const THEME_LIGHT = "light";

/** 主题取值：暗色。 */
export const THEME_DARK = "dark";

/** 主题取值：跟随系统。 */
export const THEME_SYSTEM = "system";

/** 默认主题，与后端 `DEFAULT_THEME` 保持一致。 */
export const DEFAULT_THEME = THEME_SYSTEM;

/** 支持的主题集合。 */
export const SUPPORTED_THEMES = [THEME_LIGHT, THEME_DARK, THEME_SYSTEM];

/** 默认强调色，与后端 `DEFAULT_ACCENT_COLOR` 保持一致。 */
export const DEFAULT_ACCENT_COLOR = "#00e676";

/** 目录列表默认页码。 */
export const DEFAULT_PAGE = 1;

/** 目录列表默认每页数量。 */
export const DEFAULT_PAGE_SIZE = 50;

/** 目录列表允许的最大每页数量。 */
export const MAX_PAGE_SIZE = 200;

/** 默认排序表达式。 */
export const DEFAULT_SORT = "name,asc";

/** 搜索输入防抖时间（毫秒）。 */
export const SEARCH_DEBOUNCE_MILLISECONDS = 300;

/** 请求超时时间（毫秒）。 */
export const REQUEST_TIMEOUT_MILLISECONDS = 60_000;

/** 拖拽上传时判定为「文件」还是「目录」的入口。 */
export const DATA_TRANSFER_ITEMS = "items";

/** 本地存储键：主题。 */
export const STORAGE_KEY_THEME = "fe.theme";

/** 本地存储键：强调色。 */
export const STORAGE_KEY_ACCENT_COLOR = "fe.accentColor";

/** 本地存储键：最近访问的文件夹路径。 */
export const STORAGE_KEY_RECENT_FOLDER = "fe.recentFolder";

/** 本地存储键：导航历史。 */
export const STORAGE_KEY_NAVIGATION_HISTORY = "fe.navigationHistory";

/** 本地存储键：当前排序表达式。 */
export const STORAGE_KEY_SORT = "fe.sort";

/** 本地存储键：是否显示隐藏项目。 */
export const STORAGE_KEY_SHOW_HIDDEN = "fe.showHidden";

/** 默认是否显示隐藏项目。 */
export const DEFAULT_SHOW_HIDDEN = false;

/** 文本文件预览时读取的最大字节数，超过则退化为下载。 */
export const TEXT_PREVIEW_MAX_BYTES = 2 * 1024 * 1024;

/** 分片上传的默认分片大小（5 MiB），与后端保持兼容。 */
export const DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024;

/** 分片上传并发上限。 */
export const MAX_CONCURRENT_CHUNK_UPLOADS = 4;

/** 预览模态框可展示的图片 MIME 前缀。 */
export const IMAGE_MIME_PREFIX = "image/";

/** 预览模态框可展示的文本 MIME 前缀。 */
export const TEXT_MIME_PREFIXES = ["text/", "application/json", "application/yaml"];

/** 从 URL 判断当前页面类型的路径。 */
export const PAGE_PATH_EXPLORER = "/";

/** 属性页面路径。 */
export const PAGE_PATH_METADATA = "/metadata";

/** 切换到分片上传的大小阈值（字节）。 */
export const CHUNKED_UPLOAD_THRESHOLD = 20 * 1024 * 1024;

/** 分片大小的目标数量，用于自适应计算 chunkSize。 */
export const TARGET_CHUNK_COUNT = 1000;

/** 分片大小的最小/最大边界（字节），与后端约定一致。 */
export const MIN_CHUNK_SIZE = 256 * 1024;

/** 分片大小的最大边界（字节）。 */
export const MAX_CHUNK_SIZE = 256 * 1024 * 1024;
