/**
 * 前端路由。
 *
 * 负责浏览页面 URL 的读写、浏览器前进/后退事件的分发、最近访问
 * 文件夹的记忆。路由规则：
 *
 * - `/` 或 `/?path=最近访问`：进入浏览页面；
 * - `/?path=<路径>`：进入浏览页面并展示指定路径；
 * - `/metadata?path=<路径>`：由 `metadata-page.js` 独立处理，
 *   本模块不参与。
 */

import { STORAGE_KEY_RECENT_FOLDER } from "./config.js";
import { BASE_PATH } from "./base-path.js";

/** 导航订阅者集合。 */
const navigationListeners = new Set();

/**
 * 通知所有导航订阅者。
 *
 * @param {string} path 目标路径。
 */
function notifyNavigation(path) {
  for (const listener of navigationListeners) {
    try {
      listener(path);
    } catch (error) {
      console.error("导航监听器执行失败：", error);
    }
  }
}

/**
 * 判断当前 URL 是否带有 `path` 查询参数。
 *
 * @returns {boolean} 是否带有路径参数。
 */
export function hasPathInUrl() {
  const url = new URL(window.location.href);
  return url.searchParams.has("path");
}

/**
 * 从当前 URL 解析路径。
 *
 * 无 `path` 参数时返回根路径 `/`。
 *
 * @returns {string} 沙箱虚拟路径。
 */
export function parsePathFromLocation() {
  const url = new URL(window.location.href);
  const value = url.searchParams.get("path");
  if (value === null || value === "") {
    return "/";
  }
  return value;
}

/**
 * 根据路径构造浏览页面 URL。
 *
 * 结果会带上部署路径前缀：根路径返回 `${BASE_PATH}/`，其他路径
 * 返回 `${BASE_PATH}/?path=<编码后的路径>`。当部署在根路径时，
 * `BASE_PATH` 为空串，结果退化为 `/` 与 `/?path=...`。
 *
 * @param {string} path 沙箱虚拟路径。
 * @returns {string} URL 字符串。
 */
export function buildExplorerUrl(path) {
  if (!path || path === "/") {
    return `${BASE_PATH}/`;
  }
  const parameters = new URLSearchParams();
  parameters.set("path", path);
  return `${BASE_PATH}/?${parameters.toString()}`;
}

/**
 * 读取最近访问的文件夹路径。
 *
 * @returns {string|null} 路径或 `null`。
 */
export function getRecentFolder() {
  try {
    return window.localStorage.getItem(STORAGE_KEY_RECENT_FOLDER);
  } catch (error) {
    console.error("读取最近访问文件夹失败：", error);
    return null;
  }
}

/**
 * 记录最近访问的文件夹路径。
 *
 * @param {string} path 沙箱虚拟路径。
 */
export function rememberRecentFolder(path) {
  if (!path) {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY_RECENT_FOLDER, path);
  } catch (error) {
    console.error("保存最近访问文件夹失败：", error);
  }
}

/**
 * 导航到指定路径。
 *
 * 更新浏览器历史与 URL，并通知订阅者。传入 `{ replace: true }`
 * 时使用 `replaceState`，不产生新的历史记录。
 *
 * @param {string} path 沙箱虚拟路径。
 * @param {Object} [options] 可选参数。
 * @param {boolean} [options.replace] 是否替换当前历史记录。
 * @param {boolean} [options.silent] 是否抑制订阅者通知。
 */
export function navigateTo(path, options = {}) {
  const url = buildExplorerUrl(path);
  const stateData = { path };
  if (options.replace) {
    window.history.replaceState(stateData, "", url);
  } else {
    window.history.pushState(stateData, "", url);
  }
  rememberRecentFolder(path);
  if (!options.silent) {
    notifyNavigation(path);
  }
}

/**
 * 订阅导航事件。
 *
 * 订阅者会在 `navigateTo` 调用或浏览器前进/后退时被触发。
 *
 * @param {(path: string) => void} listener 监听器。
 * @returns {() => void} 取消订阅的函数。
 */
export function subscribeToNavigation(listener) {
  navigationListeners.add(listener);
  return () => navigationListeners.delete(listener);
}

/**
 * 监听浏览器前进/后退事件。
 *
 * 从 `history.state` 中优先读取路径；无 state 时回退到 URL。
 */
window.addEventListener("popstate", (event) => {
  let path = null;
  if (event.state && typeof event.state.path === "string") {
    path = event.state.path;
  } else {
    path = parsePathFromLocation();
  }
  notifyNavigation(path);
});

/**
 * 初始化路由。
 *
 * 处理首次进入 `/` 的重定向：
 *
 * - URL 已带 `path` 参数：直接使用；
 * - URL 无 `path` 参数：使用最近访问的文件夹，无记录时使用根路径。
 *
 * 随后通知订阅者触发首次加载。应在 `subscribeToNavigation` 之后
 * 调用。
 */
export function initializeRouter() {
  if (hasPathInUrl()) {
    const path = parsePathFromLocation();
    rememberRecentFolder(path);
    notifyNavigation(path);
    return;
  }

  const initialPath = getRecentFolder() || "/";
  const targetUrl = buildExplorerUrl(initialPath);
  if (window.location.pathname + window.location.search !== targetUrl) {
    window.history.replaceState({ path: initialPath }, "", targetUrl);
  }
  rememberRecentFolder(initialPath);
  notifyNavigation(initialPath);
}
