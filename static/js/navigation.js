/**
 * 导航逻辑：路径输入跳转、后退/前进/上级、分页。
 */

import { getElement } from "./dom.js";
import { loadDirectory } from "./rendering.js";
import { state } from "./state.js";

/**
 * 绑定导航相关事件。
 */
export function initNavigation() {
  getElement("path-input").addEventListener("keydown", onPathInputKeydown);
  getElement("back-button").addEventListener("click", goBack);
  getElement("forward-button").addEventListener("click", goForward);
  getElement("up-button").addEventListener("click", goUp);
  getElement("refresh-button").addEventListener("click", reloadFromState);
  getElement("prev-page-button").addEventListener("click", changePageBy);
  getElement("next-page-button").addEventListener("click", changePageBy);
}

/**
 * 路径输入框回车跳转。
 * @param {KeyboardEvent} event - 键盘事件
 */
function onPathInputKeydown(event) {
  if (event.key === "Enter") {
    const target = getElement("path-input").value.trim() || "/";
    navigateToPath(target);
  }
}

/**
 * 跳转到新路径（维护前进/后退历史）。
 * @param {string} targetPath - 目标路径
 */
export function navigateToPath(targetPath) {
  state.historyBack.push(state.currentPath);
  state.historyForward = [];
  state.currentPath = targetPath;
  state.page = 1;
  state.isSearching = false;
  getElement("search-input").value = "";
  reloadFromState();
}

/**
 * 后退到上一个目录。
 */
function goBack() {
  if (state.historyBack.length === 0) {
    return;
  }
  state.historyForward.push(state.currentPath);
  state.currentPath = state.historyBack.pop();
  reloadFromState();
}

/**
 * 前进到下一个目录。
 */
function goForward() {
  if (state.historyForward.length === 0) {
    return;
  }
  state.historyBack.push(state.currentPath);
  state.currentPath = state.historyForward.pop();
  reloadFromState();
}

/**
 * 进入上一级目录。
 */
function goUp() {
  if (state.currentPath === "/") {
    return;
  }
  const parent = state.currentPath.replace(/\/[^/]*$/, "") || "/";
  navigateToPath(parent);
}

/**
 * 翻页。
 * @param {MouseEvent} event - 点击事件
 */
function changePageBy(event) {
  const direction = event.target === getElement("next-page-button") ? 1 : -1;
  state.page += direction;
  loadDirectory();
}

/**
 * 按当前状态重新加载目录。
 */
function reloadFromState() {
  loadDirectory();
}
