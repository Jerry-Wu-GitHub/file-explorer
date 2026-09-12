/**
 * 目录加载与搜索编排。
 *
 * 把「加载当前路径 → 更新状态 → 触发渲染」的流程集中在一处，
 * 供 `main.js`、工具栏、右键菜单、键盘快捷键与路由统一调用。
 *
 * 加载过程只更新状态，渲染由 `state.js` 的订阅者完成。
 */

import { listDirectory, searchEntries } from "./api/files.js";
import {
  getSortExpression,
  getState,
  setCurrentPath,
  setEntries,
  setError,
  setLoading,
  setPagination,
  setSelection,
} from "./state.js";

/** 当前激活的搜索关键词；为 `null` 时表示常规目录浏览。 */
let activeSearchQuery = null;

/** 最近一次加载使用的页码。 */
let currentPage = 1;

/**
 * 过滤隐藏项。
 *
 * 后端返回全部条目（含隐藏项），由前端按用户偏好过滤。
 *
 * @param {Object[]} entries 条目列表。
 * @param {boolean} showHidden 是否显示隐藏项。
 * @returns {Object[]} 过滤后的条目列表。
 */
function filterHidden(entries, showHidden) {
  if (showHidden) {
    return entries;
  }
  return entries.filter((entry) => !entry.isHidden);
}

/**
 * 按当前状态构造分页信息。
 *
 * @param {Object|null} meta 后端返回的 meta。
 * @param {number} fallbackPage 请求使用的页码。
 * @param {number} fallbackSize 请求使用的每页数量。
 * @param {number} fallbackTotal 后端未返回 total 时使用的条数。
 * @returns {{page: number, size: number, total: number}} 分页信息。
 */
function buildPagination(meta, fallbackPage, fallbackSize, fallbackTotal) {
  return {
    page: meta?.page ?? fallbackPage,
    size: meta?.size ?? fallbackSize,
    total: meta?.total ?? fallbackTotal,
  };
}

/**
 * 从后端加载当前上下文（目录或搜索结果）。
 *
 * @param {number} page 目标页码，从 1 开始。
 * @returns {Promise<void>} 无返回值。
 */
async function fetchEntries(page) {
  const state = getState();
  const pageSize = state.pagination.size;
  setLoading(true);
  setError(null);

  try {
    const parameters = {
      page,
      size: pageSize,
      followLink: true,
    };

    let result;
    if (activeSearchQuery !== null) {
      result = await searchEntries({
        ...parameters,
        q: activeSearchQuery,
        path: state.currentPath,
      });
    } else {
      result = await listDirectory(state.currentPath, {
        ...parameters,
        sort: getSortExpression(),
        type: "all",
      });
    }

    const rawEntries = Array.isArray(result.data) ? result.data : [];
    const visibleEntries = filterHidden(rawEntries, state.showHidden);
    setEntries(visibleEntries);
    setPagination(
      buildPagination(result.meta, page, pageSize, visibleEntries.length)
    );
    currentPage = page;
  } catch (error) {
    setEntries([]);
    setError(error);
  } finally {
    setLoading(false);
  }
}

/**
 * 加载指定路径。
 *
 * 清除当前搜索关键词与选中集合，然后加载目录内容。
 *
 * @param {string} path 目标沙箱虚拟路径。
 * @param {Object} [options] 可选参数。
 * @param {number} [options.page] 目标页码，默认第 1 页。
 * @returns {Promise<void>} 无返回值。
 */
export async function loadPath(path, options = {}) {
  activeSearchQuery = null;
  setCurrentPath(path);
  setSelection([]);
  await fetchEntries(options.page || 1);
}

/**
 * 在当前目录内运行搜索。
 *
 * @param {string} query 搜索关键词。
 * @param {Object} [options] 可选参数。
 * @param {number} [options.page] 目标页码，默认第 1 页。
 * @returns {Promise<void>} 无返回值。
 */
export async function runSearch(query, options = {}) {
  activeSearchQuery = query;
  setSelection([]);
  await fetchEntries(options.page || 1);
}

/**
 * 清空搜索并恢复当前目录的常规浏览。
 *
 * @returns {Promise<void>} 无返回值。
 */
export async function clearSearch() {
  activeSearchQuery = null;
  setSelection([]);
  await fetchEntries(1);
}

/**
 * 重新加载当前上下文。
 *
 * 若用户正在进行搜索，则保留搜索关键词；否则按目录刷新。
 *
 * @returns {Promise<void>} 无返回值。
 */
export async function reloadCurrentContext() {
  await fetchEntries(currentPage);
}

/**
 * 跳转到指定页。
 *
 * @param {number} page 目标页码。
 * @returns {Promise<void>} 无返回值。
 */
export async function goToPage(page) {
  const target = Math.max(1, Math.floor(page));
  await fetchEntries(target);
}

/**
 * 跳转到下一页。
 *
 * @returns {Promise<void>} 无返回值。
 */
export async function goToNextPage() {
  const state = getState();
  const totalPages = Math.max(
    1,
    Math.ceil(state.pagination.total / state.pagination.size)
  );
  if (state.pagination.page >= totalPages) {
    return;
  }
  await goToPage(state.pagination.page + 1);
}

/**
 * 跳转到上一页。
 *
 * @returns {Promise<void>} 无返回值。
 */
export async function goToPreviousPage() {
  const state = getState();
  if (state.pagination.page <= 1) {
    return;
  }
  await goToPage(state.pagination.page - 1);
}

/**
 * 返回当前是否处于搜索模式。
 *
 * @returns {boolean} 是否处于搜索模式。
 */
export function isSearching() {
  return activeSearchQuery !== null;
}

/**
 * 返回当前搜索关键词。
 *
 * @returns {string|null} 搜索关键词或 `null`。
 */
export function getActiveSearchQuery() {
  return activeSearchQuery;
}

/**
 * 计算当前上下文的总页数。
 *
 * @returns {number} 总页数，至少为 1。
 */
export function getTotalPages() {
  const state = getState();
  const { total, size } = state.pagination;
  if (size <= 0) {
    return 1;
  }
  return Math.max(1, Math.ceil(total / size));
}
