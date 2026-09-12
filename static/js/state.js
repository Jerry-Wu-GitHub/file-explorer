/**
 * 前端全局状态。
 *
 * 集中管理浏览页面所需的状态：当前路径、条目列表、选中集合、
 * 剪贴板、分页、排序、隐藏项开关与加载状态。其他模块通过
 * `getState()` 读取快照，通过 `subscribe(listener)` 订阅变更，
 * 通过导出的 setter 修改状态。
 *
 * 状态更新遵循不可变原则：每次修改都创建新对象，便于 diff 与
 * 调试；订阅者在每次 setter 调用后收到完整快照。
 */

import {
  DEFAULT_PAGE,
  DEFAULT_PAGE_SIZE,
  DEFAULT_SHOW_HIDDEN,
  DEFAULT_SORT,
} from "./config.js";

/**
 * 解析排序表达式 `<字段>,<方向>`。
 *
 * @param {string} expression 排序表达式。
 * @returns {{field: string, direction: string}} 排序对象。
 */
export function parseSortExpression(expression) {
  const parts = String(expression || "").split(",");
  const field = parts[0] || "name";
  const direction = parts[1] === "desc" ? "desc" : "asc";
  return { field, direction };
}

/**
 * 将排序对象序列化为表达式字符串。
 *
 * @param {{field: string, direction: string}} sort 排序对象。
 * @returns {string} 表达式字符串。
 */
export function buildSortExpression(sort) {
  return `${sort.field},${sort.direction}`;
}

/** 内部状态对象。仅供本模块修改。 */
let currentState = {
  currentPath: "/",
  entries: [],
  selectedPaths: [],
  clipboard: null,
  pagination: { page: DEFAULT_PAGE, size: DEFAULT_PAGE_SIZE, total: 0 },
  sort: parseSortExpression(DEFAULT_SORT),
  showHidden: DEFAULT_SHOW_HIDDEN,
  loading: false,
  error: null,
};

/** 订阅者集合。 */
const listeners = new Set();

/**
 * 通知所有订阅者。
 */
function notify() {
  const snapshot = getState();
  for (const listener of listeners) {
    try {
      listener(snapshot);
    } catch (error) {
      console.error("状态监听器执行失败：", error);
    }
  }
}

/**
 * 合并状态片段并通知订阅者。
 *
 * @param {Object} patch 要更新的字段。
 */
function updateState(patch) {
  currentState = { ...currentState, ...patch };
  notify();
}

/**
 * 返回当前状态的浅拷贝快照。
 *
 * 数组与嵌套对象均为拷贝，避免调用方意外修改内部状态。
 *
 * @returns {Object} 状态快照。
 */
export function getState() {
  return {
    ...currentState,
    pagination: { ...currentState.pagination },
    sort: { ...currentState.sort },
    selectedPaths: [...currentState.selectedPaths],
    clipboard: currentState.clipboard
      ? {
          mode: currentState.clipboard.mode,
          paths: [...currentState.clipboard.paths],
        }
      : null,
  };
}

/**
 * 注册状态变更监听器。
 *
 * @param {(snapshot: Object) => void} listener 监听器。
 * @returns {() => void} 取消订阅的函数。
 */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * 重置状态为初始值。
 */
export function resetState() {
  currentState = {
    currentPath: "/",
    entries: [],
    selectedPaths: [],
    clipboard: null,
    pagination: { page: DEFAULT_PAGE, size: DEFAULT_PAGE_SIZE, total: 0 },
    sort: parseSortExpression(DEFAULT_SORT),
    showHidden: DEFAULT_SHOW_HIDDEN,
    loading: false,
    error: null,
  };
  notify();
}

/* ---------------------------------------------------------------------------
 * 路径与条目
 * ------------------------------------------------------------------------ */

/**
 * 设置当前路径。
 *
 * @param {string} path 沙箱虚拟路径。
 */
export function setCurrentPath(path) {
  updateState({ currentPath: path });
}

/**
 * 设置条目列表。
 *
 * @param {Object[]} entries 条目元数据列表。
 */
export function setEntries(entries) {
  updateState({ entries: [...entries] });
}

/**
 * 设置分页信息。
 *
 * @param {{page: number, size: number, total: number}} pagination 分页信息。
 */
export function setPagination(pagination) {
  updateState({ pagination: { ...pagination } });
}

/**
 * 设置排序字段与方向。
 *
 * @param {string} field 排序字段。
 * @param {string} direction 排序方向。
 */
export function setSort(field, direction) {
  updateState({ sort: { field, direction } });
}

/**
 * 通过表达式设置排序。
 *
 * @param {string} expression 排序表达式。
 */
export function setSortExpression(expression) {
  updateState({ sort: parseSortExpression(expression) });
}

/**
 * 返回当前排序表达式。
 *
 * @returns {string} 表达式字符串。
 */
export function getSortExpression() {
  return buildSortExpression(currentState.sort);
}

/**
 * 设置是否显示隐藏项目。
 *
 * @param {boolean} showHidden 是否显示。
 */
export function setShowHidden(showHidden) {
  updateState({ showHidden: Boolean(showHidden) });
}

/**
 * 设置加载状态。
 *
 * @param {boolean} loading 是否处于加载中。
 */
export function setLoading(loading) {
  updateState({ loading: Boolean(loading) });
}

/**
 * 设置错误信息。
 *
 * @param {Error|Object|null} error 错误对象，传 `null` 清除。
 */
export function setError(error) {
  updateState({ error: error || null });
}

/* ---------------------------------------------------------------------------
 * 选中集合
 * ------------------------------------------------------------------------ */

/**
 * 全量替换选中路径。
 *
 * @param {string[]} paths 路径列表。
 */
export function setSelection(paths) {
  const unique = [...new Set(paths)];
  updateState({ selectedPaths: unique });
}

/**
 * 向选中集合添加路径。
 *
 * @param {string[]} paths 路径列表。
 */
export function addToSelection(paths) {
  const merged = new Set([...currentState.selectedPaths, ...paths]);
  updateState({ selectedPaths: [...merged] });
}

/**
 * 从选中集合移除路径。
 *
 * @param {string[]} paths 路径列表。
 */
export function removeFromSelection(paths) {
  const removed = new Set(paths);
  updateState({
    selectedPaths: currentState.selectedPaths.filter(
      (path) => !removed.has(path)
    ),
  });
}

/**
 * 切换某个路径的选中状态。
 *
 * @param {string} path 路径。
 */
export function toggleSelection(path) {
  const set = new Set(currentState.selectedPaths);
  if (set.has(path)) {
    set.delete(path);
  } else {
    set.add(path);
  }
  updateState({ selectedPaths: [...set] });
}

/**
 * 清空选中集合。
 */
export function clearSelection() {
  if (currentState.selectedPaths.length === 0) {
    return;
  }
  updateState({ selectedPaths: [] });
}

/**
 * 判断某个路径是否被选中。
 *
 * @param {string} path 路径。
 * @returns {boolean} 是否选中。
 */
export function isSelected(path) {
  return currentState.selectedPaths.includes(path);
}

/**
 * 返回当前选中路径对应的条目列表。
 *
 * @returns {Object[]} 选中的条目。
 */
export function getSelectedEntries() {
  const selected = new Set(currentState.selectedPaths);
  return currentState.entries.filter((entry) => selected.has(entry.path));
}

/* ---------------------------------------------------------------------------
 * 剪贴板
 * ------------------------------------------------------------------------ */

/**
 * 设置剪贴板内容。
 *
 * @param {"copy"|"cut"} mode 模式。
 * @param {string[]} paths 路径列表。
 */
export function setClipboard(mode, paths) {
  updateState({ clipboard: { mode, paths: [...paths] } });
}

/**
 * 清空剪贴板。
 */
export function clearClipboard() {
  updateState({ clipboard: null });
}

/**
 * 判断剪贴板是否有内容。
 *
 * @returns {boolean} 是否有内容。
 */
export function hasClipboard() {
  return (
    currentState.clipboard !== null &&
    currentState.clipboard.paths.length > 0
  );
}
