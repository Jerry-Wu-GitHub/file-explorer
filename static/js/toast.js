/**
 * 全局提示。
 *
 * 提供成功、错误、信息三类提示，统一渲染到 `#toast-container`，
 * 并在指定时长后自动淡出。堆叠数量有上限，避免刷屏。
 */

/** 容器中同时存在的 toast 最大数量。 */
const MAX_VISIBLE_TOASTS = 3;

/** 默认展示时长（毫秒）。 */
const DEFAULT_DURATION = 3000;

/** 错误提示的默认展示时长（毫秒）。 */
const ERROR_DURATION = 5000;

/** 淡出动画时长（毫秒），与 CSS 中保持一致。 */
const FADE_OUT_DURATION = 200;

/**
 * 从任意错误对象中提取可读的提示文案。
 *
 * 优先使用后端返回的业务错误码与文案；退化到 `Error.message`；
 * 最后返回兜底文案。
 *
 * @param {*} error 错误对象或字符串。
 * @returns {string} 可读文案。
 */
export function extractErrorMessage(error) {
  if (!error) {
    return "未知错误";
  }
  if (typeof error === "string") {
    return error;
  }
  if (typeof error.code === "string" && typeof error.message === "string") {
    return `${error.message}（${error.code}）`;
  }
  if (typeof error.message === "string" && error.message !== "") {
    return error.message;
  }
  return "未知错误";
}

/**
 * 获取或惰性创建 toast 容器。
 *
 * @returns {HTMLElement|null} 容器元素。
 */
function getContainer() {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    container.setAttribute("aria-live", "polite");
    document.body.appendChild(container);
  }
  return container;
}

/**
 * 裁剪容器内的 toast 数量，保持不超过上限。
 *
 * @param {HTMLElement} container 容器元素。
 */
function trimContainer(container) {
  while (container.children.length >= MAX_VISIBLE_TOASTS) {
    container.firstElementChild?.remove();
  }
}

/**
 * 移除单个 toast，带淡出动画。
 *
 * @param {HTMLElement} element toast 元素。
 */
function dismiss(element) {
  if (!element.isConnected) {
    return;
  }
  element.classList.add("hiding");
  window.setTimeout(() => element.remove(), FADE_OUT_DURATION);
}

/**
 * 展示一条提示。
 *
 * @param {string} message 提示文案。
 * @param {Object} [options] 可选参数。
 * @param {"info"|"success"|"error"} [options.type] 提示类型。
 * @param {number} [options.duration] 展示时长（毫秒）。
 * @returns {HTMLElement|null} 创建的 toast 元素。
 */
export function showToast(message, options = {}) {
  const container = getContainer();
  if (!container) {
    return null;
  }
  trimContainer(container);

  const element = document.createElement("div");
  element.className = "toast";
  if (options.type === "success") {
    element.classList.add("toast--success");
  } else if (options.type === "error") {
    element.classList.add("toast--error");
  }
  element.textContent = String(message);
  element.addEventListener("click", () => dismiss(element));

  container.appendChild(element);

  const duration =
    options.duration ??
    (options.type === "error" ? ERROR_DURATION : DEFAULT_DURATION);
  if (duration > 0) {
    window.setTimeout(() => dismiss(element), duration);
  }
  return element;
}

/**
 * 展示成功提示。
 *
 * @param {string} message 提示文案。
 * @returns {HTMLElement|null} 创建的 toast 元素。
 */
export function showSuccess(message) {
  return showToast(message, { type: "success" });
}

/**
 * 展示错误提示。
 *
 * 接受字符串或任意错误对象（含 `ApiError`）。
 *
 * @param {*} error 错误对象或字符串。
 * @returns {HTMLElement|null} 创建的 toast 元素。
 */
export function showError(error) {
  return showToast(extractErrorMessage(error), { type: "error" });
}

/**
 * 展示信息提示。
 *
 * @param {string} message 提示文案。
 * @returns {HTMLElement|null} 创建的 toast 元素。
 */
export function showInfo(message) {
  return showToast(message, { type: "info" });
}

/**
 * 清空所有正在展示的 toast。
 */
export function clearAllToasts() {
  const container = document.getElementById("toast-container");
  if (!container) {
    return;
  }
  for (const child of [...container.children]) {
    child.remove();
  }
}
