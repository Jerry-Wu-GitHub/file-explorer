/**
 * 文件浏览器共享状态：视图状态与刷新调度。
 */

/** 视图状态（跨模块共享） */
export const state = {
  currentPath: "/",
  page: 1,
  sortField: "name",
  sortDirection: "asc",
  showHidden: false,
  total: 0,
  selection: new Map(),
  clipboard: null,
  historyBack: [],
  historyForward: [],
  searchKeyword: "",
  isSearching: false,
};

/** 重新加载回调 */
let reloadHandler = null;

/** 工具栏刷新回调 */
let toolbarHandler = null;

/**
 * 注册重新加载处理器（由视图模块在初始化时调用）。
 * @param {Function} handler - 重新加载函数
 */
export function setReloadHandler(handler) {
  reloadHandler = handler;
}

/**
 * 注册工具栏刷新处理器（由视图模块在初始化时调用）。
 * @param {Function} handler - 工具栏刷新函数
 */
export function setToolbarHandler(handler) {
  toolbarHandler = handler;
}

/**
 * 触发当前目录重新加载。
 */
export function reloadDirectory() {
  if (reloadHandler) {
    reloadHandler();
  }
}

/**
 * 触发工具栏状态刷新。
 */
export function refreshToolbar() {
  if (toolbarHandler) {
    toolbarHandler();
  }
}

/**
 * 返回选中条目的路径列表。
 * @returns {string[]} 选中路径
 */
export function selectedPaths() {
  return [...state.selection.keys()];
}
