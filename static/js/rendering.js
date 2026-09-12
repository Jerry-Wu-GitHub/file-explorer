/**
 * 目录渲染：加载目录、构建条目、更新状态栏与错误提示。
 */

import { listFiles, searchFiles } from "./api.js";
import { getElement } from "./dom.js";
import {
  escapeHtml,
  formatFileSize,
  formatTimestamp,
  iconForEntry,
  storeLastFolder,
} from "./utils.js";
import { refreshToolbar, state } from "./state.js";

/** 前端每页展示数量 */
const PAGE_SIZE = 200;

/**
 * 加载并渲染当前目录。
 */
export async function loadDirectory() {
  refreshToolbar();
  try {
    const result = state.isSearching
      ? await searchFiles({
          q: state.searchKeyword,
          path: state.currentPath,
          type: "all",
          page: state.page,
          size: PAGE_SIZE,
        })
      : await listFiles({
          path: state.currentPath,
          page: state.page,
          size: PAGE_SIZE,
          sort: `${state.sortField},${state.sortDirection}`,
          type: "all",
        });

    state.total = result.meta.total;
    renderEntries(result.data);
    updateStatusBar();
    getElement("path-input").value = state.currentPath;
    if (!state.isSearching && state.total > 0) {
      storeLastFolder(state.currentPath);
    }
  } catch (error) {
    renderError(error.message);
  }
}

/**
 * 渲染条目网格。
 * @param {object[]} entries - 条目列表
 */
function renderEntries(entries) {
  const grid = getElement("file-grid");
  grid.innerHTML = "";
  state.selection.clear();
  refreshToolbar();

  const visibleEntries = state.showHidden
    ? entries
    : entries.filter((entry) => !entry.isHidden);

  if (visibleEntries.length === 0) {
    grid.innerHTML = `<div class="empty-hint">${state.isSearching ? "没有匹配的搜索结果" : "文件夹为空"}</div>`;
    return;
  }

  for (const entry of visibleEntries) {
    grid.appendChild(buildEntryElement(entry));
  }
}

/**
 * 构建单个条目元素。
 * @param {object} entry - 文件系统条目
 * @returns {HTMLElement} 条目 DOM
 */
function buildEntryElement(entry) {
  const item = document.createElement("div");
  item.className = `file-item ${entry.type}`;
  if (entry.isHidden) {
    item.classList.add("hidden-item");
  }
  item.dataset.path = entry.path;
  item.dataset.type = entry.type;

  const detailText =
    entry.type === "directory"
      ? formatTimestamp(entry.modifiedAt)
      : `${formatFileSize(entry.size)} · ${formatTimestamp(entry.modifiedAt)}`;

  item.innerHTML = `
    <div class="file-icon">${iconForEntry(entry)}</div>
    <div class="file-name" title="${escapeHtml(entry.path)}">${escapeHtml(entry.name)}</div>
    <div class="file-detail">${escapeHtml(detailText)}</div>
  `;
  return item;
}

/**
 * 更新状态栏信息与分页。
 */
function updateStatusBar() {
  getElement("status-info").textContent = `${state.currentPath} — 共 ${state.total} 项`;
  const totalPages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
  getElement("page-info").textContent = `${state.page} / ${totalPages}`;
  getElement("prev-page-button").disabled = state.page <= 1;
  getElement("next-page-button").disabled = state.page >= totalPages;
}

/**
 * 渲染错误提示到网格。
 * @param {string} message - 错误文案
 */
function renderError(message) {
  getElement("file-grid").innerHTML = `<div class="empty-hint">加载失败：${escapeHtml(message)}</div>`;
  getElement("status-info").textContent = message;
}
