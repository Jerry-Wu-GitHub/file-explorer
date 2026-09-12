/**
 * 前端通用工具函数：格式化、DOM 辅助、本地存储等。
 */

/** 最近访问文件夹的本地存储键名 */
const LAST_FOLDER_KEY = "file-explorer.lastFolder";

/**
 * 将字节数格式化为人类可读大小。
 * @param {number} bytes - 字节数
 * @returns {string} 格式化结果，如 1.5 MiB
 */
export function formatFileSize(bytes) {
  if (bytes === 0) {
    return "0 B";
  }
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const digits = value >= 100 ? 0 : value >= 10 ? 1 : 2;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

/**
 * 将 Unix 时间戳格式化为本地时间字符串。
 * @param {number} timestamp - Unix 时间戳（秒）
 * @returns {string} 格式化时间
 */
export function formatTimestamp(timestamp) {
  if (timestamp === undefined || timestamp === null) {
    return "-";
  }
  const date = new Date(timestamp * 1000);
  return date.toLocaleString("zh-CN", { hour12: false });
}

/**
 * 转义 HTML 特殊字符，防止 XSS。
 * @param {string} text - 原始文本
 * @returns {string} 转义后的文本
 */
export function escapeHtml(text) {
  const container = document.createElement("div");
  container.textContent = String(text);
  return container.innerHTML;
}

/**
 * 根据条目类型返回图标字符。
 * @param {object} entry - 文件系统条目
 * @returns {string} 图标字符
 */
export function iconForEntry(entry) {
  if (entry.type === "directory") {
    return "&#128193;";
  }
  if (entry.type === "link") {
    return "&#128279;";
  }
  return "&#128196;";
}

/**
 * 判断 MIME 类型是否为可文本预览类型。
 * @param {string} mimeType - MIME 类型
 * @returns {boolean} 是否可文本预览
 */
export function isTextPreviewable(mimeType) {
  if (!mimeType) {
    return false;
  }
  return (
    mimeType.startsWith("text/") ||
    mimeType === "application/json" ||
    mimeType === "application/javascript" ||
    mimeType === "application/xml" ||
    mimeType.endsWith("+json") ||
    mimeType.endsWith("+xml")
  );
}

/**
 * 判断 MIME 类型是否为图片。
 * @param {string} mimeType - MIME 类型
 * @returns {boolean} 是否为图片
 */
export function isImageType(mimeType) {
  return mimeType !== null && mimeType !== undefined && mimeType.startsWith("image/");
}

/**
 * 解析当前页面查询参数。
 * @returns {URLSearchParams} 查询参数对象
 */
export function parseQueryParams() {
  return new URLSearchParams(window.location.search);
}

/**
 * 读取最近访问文件夹。
 * @returns {string} 最近访问的文件夹路径，无记录时返回 "/"
 */
export function readLastFolder() {
  const stored = localStorage.getItem(LAST_FOLDER_KEY);
  return stored && stored.startsWith("/") ? stored : "/";
}

/**
 * 记录最近访问文件夹。
 * @param {string} path - 文件夹路径
 */
export function storeLastFolder(path) {
  localStorage.setItem(LAST_FOLDER_KEY, path);
}

/**
 * 延时执行器：用于搜索输入防抖。
 */
export class Debouncer {
  /**
   * @param {number} delayMilliseconds - 延时毫秒数
   */
  constructor(delayMilliseconds) {
    this.delayMilliseconds = delayMilliseconds;
    this.timerId = null;
  }

  /**
   * 在延时后执行回调，之前的未执行回调会被取消。
   * @param {Function} callback - 待执行的回调
   */
  run(callback) {
    clearTimeout(this.timerId);
    this.timerId = setTimeout(callback, this.delayMilliseconds);
  }
}

/**
 * 跳转到指定路径的文件浏览器页面。
 * @param {string} path - 目标虚拟路径
 */
export function navigateTo(path) {
  window.location.href = `/?path=${encodeURIComponent(path)}`;
}
