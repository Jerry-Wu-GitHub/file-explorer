/**
 * 路径栏交互。
 *
 * 负责：
 *
 * - 回退 / 前进 / 上一级 / 刷新按钮；
 * - 路径输入框的 Enter 提交、聚焦全选与失焦恢复；
 * - 搜索框的输入防抖与 Escape 清空。
 *
 * 本模块不直接修改状态；导航通过 `router.navigateTo` 完成，刷新
 * 与搜索通过回调交由 `main.js` 协调。
 */

import { SEARCH_DEBOUNCE_MILLISECONDS } from "./config.js";
import { navigateTo } from "./router.js";
import { getState } from "./state.js";

/** 回调集合，由 `initializePathBar` 注入。 */
let callbacks = {
  onRefresh: () => {},
  onSearch: () => {},
  onSearchClear: () => {},
};

/** 是否已初始化。 */
let initialized = false;

/** 搜索输入防抖定时器 ID。 */
let searchTimerId = 0;

/**
 * 计算某个虚拟路径的上一级目录。
 *
 * 根路径的上一级仍是根路径。
 *
 * @param {string} path 沙箱虚拟路径。
 * @returns {string} 上一级路径。
 */
export function computeParentPath(path) {
  if (!path || path === "/") {
    return "/";
  }
  const segments = path.split("/").filter(Boolean);
  segments.pop();
  if (segments.length === 0) {
    return "/";
  }
  return `/${segments.join("/")}`;
}

/**
 * 处理路径输入框的按键。
 *
 * @param {KeyboardEvent} event 键盘事件。
 */
function handlePathInputKeydown(event) {
  if (event.key !== "Enter") {
    return;
  }
  event.preventDefault();
  const value = event.target.value.trim() || "/";
  navigateTo(value);
  event.target.blur();
}

/**
 * 处理路径输入框获得焦点：全选便于直接覆盖输入。
 *
 * @param {FocusEvent} event 焦点事件。
 */
function handlePathInputFocus(event) {
  event.target.select();
}

/**
 * 处理路径输入框失去焦点：恢复为当前路径。
 *
 * @param {FocusEvent} event 焦点事件。
 */
function handlePathInputBlur(event) {
  event.target.value = getState().currentPath;
}

/**
 * 处理搜索框输入：防抖后触发搜索或清空回调。
 *
 * @param {InputEvent} event 输入事件。
 */
function handleSearchInput(event) {
  if (searchTimerId) {
    window.clearTimeout(searchTimerId);
  }
  const query = event.target.value;
  searchTimerId = window.setTimeout(() => {
    searchTimerId = 0;
    if (query.trim() === "") {
      callbacks.onSearchClear();
    } else {
      callbacks.onSearch(query.trim());
    }
  }, SEARCH_DEBOUNCE_MILLISECONDS);
}

/**
 * 处理搜索框按键：Escape 清空并失焦。
 *
 * @param {KeyboardEvent} event 键盘事件。
 */
function handleSearchKeydown(event) {
  if (event.key !== "Escape") {
    return;
  }
  event.target.value = "";
  callbacks.onSearchClear();
  event.target.blur();
}

/**
 * 初始化路径栏。
 *
 * 应在 `main.js` 中调用一次，并注入刷新与搜索回调。
 *
 * @param {Object} [options] 回调集合。
 * @param {() => void} [options.onRefresh] 刷新当前目录。
 * @param {(query: string) => void} [options.onSearch] 搜索关键词。
 * @param {() => void} [options.onSearchClear] 清空搜索并恢复目录。
 */
export function initializePathBar(options = {}) {
  if (initialized) {
    return;
  }
  initialized = true;
  callbacks = { ...callbacks, ...options };

  document.getElementById("back-button")?.addEventListener("click", () => {
    window.history.back();
  });
  document.getElementById("forward-button")?.addEventListener("click", () => {
    window.history.forward();
  });
  document.getElementById("up-button")?.addEventListener("click", () => {
    navigateTo(computeParentPath(getState().currentPath));
  });
  document.getElementById("refresh-button")?.addEventListener("click", () => {
    callbacks.onRefresh();
  });

  const pathInput = document.getElementById("path-input");
  pathInput?.addEventListener("keydown", handlePathInputKeydown);
  pathInput?.addEventListener("focus", handlePathInputFocus);
  pathInput?.addEventListener("blur", handlePathInputBlur);

  const searchInput = document.getElementById("search-input");
  searchInput?.addEventListener("input", handleSearchInput);
  searchInput?.addEventListener("keydown", handleSearchKeydown);
}

/**
 * 根据状态快照更新路径栏。
 *
 * @param {Object} state 状态快照。
 */
export function renderPathBar(state) {
  const pathInput = document.getElementById("path-input");
  if (pathInput && document.activeElement !== pathInput) {
    pathInput.value = state.currentPath;
  }

  const upButton = document.getElementById("up-button");
  if (upButton) {
    upButton.disabled = state.currentPath === "/";
  }
}

/**
 * 将焦点移至搜索框并选中已有内容。
 */
export function focusSearchInput() {
  const input = document.getElementById("search-input");
  if (input) {
    input.focus();
    input.select();
  }
}

/**
 * 清空搜索框内容。
 */
export function clearSearchInput() {
  const input = document.getElementById("search-input");
  if (input) {
    input.value = "";
  }
}
