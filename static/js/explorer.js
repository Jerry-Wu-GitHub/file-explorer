/**
 * 文件浏览器视图：初始化、工具栏、搜索、隐藏开关。
 */

import { Debouncer, parseQueryParams, readLastFolder } from "./utils.js";
import { cacheElements } from "./dom.js";
import { executeAction } from "./actions.js";
import { initDragSelect } from "./dragselect.js";
import { bindShortcuts } from "./shortcuts.js";
import { closeAllMenus, initMenus, showNewMenu, showSortMenu } from "./menus.js";
import { initNavigation } from "./navigation.js";
import { initSelection } from "./selection.js";
import { loadDirectory } from "./rendering.js";
import { setReloadHandler, setToolbarHandler, state } from "./state.js";

/** 搜索防抖器 */
const searchDebouncer = new Debouncer(350);

/** 视图元素 ID 列表 */
const elementIds = [
  "path-input", "search-input", "file-grid", "status-info",
  "prev-page-button", "next-page-button", "page-info",
  "new-button", "cut-button", "copy-button", "paste-button",
  "rename-button", "share-button", "delete-button", "sort-button",
  "show-hidden-checkbox", "preview-modal", "preview-title",
  "preview-body", "preview-close-button",
];

/**
 * 初始化文件浏览器视图。
 */
export function initExplorer() {
  cacheElements(elementIds);
  initMenus();
  setReloadHandler(loadDirectory);
  setToolbarHandler(updateToolbarState);
  bindToolbar();
  bindViewEvents();
  initNavigation();
  initSelection();
  initDragSelect(document.getElementById("file-grid"));
  bindShortcuts(document.getElementById("search-input"));
  resolveInitialPath();
  loadDirectory();
}

/**
 * 绑定工具栏按钮事件。
 */
function bindToolbar() {
  const toolActions = ["cut", "copy", "paste", "rename", "share", "delete"];
  for (const action of toolActions) {
    document.getElementById(`${action}-button`).addEventListener("click", () => executeAction(action));
  }
  document.getElementById("new-button").addEventListener("click", onNewButtonClick);
  document.getElementById("sort-button").addEventListener("click", onSortButtonClick);
}

/**
 * 绑定视图级事件。
 */
function bindViewEvents() {
  document.getElementById("search-input").addEventListener("input", onSearchInput);
  document.getElementById("show-hidden-checkbox").addEventListener("change", onShowHiddenChange);
  document.addEventListener("click", closeAllMenus);
  document.getElementById("preview-close-button").addEventListener("click", closePreview);
}

/**
 * 解析初始路径：URL 参数 > 最近访问 > 根目录。
 */
function resolveInitialPath() {
  const params = parseQueryParams();
  const requested = params.get("path");
  state.currentPath = requested ? requested : readLastFolder();
}

/**
 * 搜索输入防抖触发。
 * @param {Event} event - 输入事件
 */
function onSearchInput(event) {
  const keyword = event.target.value.trim();
  searchDebouncer.run(() => runSearch(keyword));
}

/**
 * 执行搜索并渲染。
 * @param {string} keyword - 搜索关键词
 */
function runSearch(keyword) {
  state.searchKeyword = keyword;
  state.isSearching = keyword.length > 0;
  state.page = 1;
  loadDirectory();
}

/**
 * 显示隐藏项开关。
 * @param {Event} event - 变更事件
 */
function onShowHiddenChange(event) {
  state.showHidden = event.target.checked;
  loadDirectory();
}

/**
 * 更新工具栏按钮可用状态。
 */
function updateToolbarState() {
  const hasSelection = state.selection.size > 0;
  document.getElementById("cut-button").disabled = !hasSelection;
  document.getElementById("copy-button").disabled = !hasSelection;
  document.getElementById("rename-button").disabled = !hasSelection;
  document.getElementById("share-button").disabled = !hasSelection;
  document.getElementById("delete-button").disabled = !hasSelection;
  document.getElementById("paste-button").disabled = state.clipboard === null;
}

/**
 * 新建按钮点击：显示下拉菜单。
 * @param {MouseEvent} event - 鼠标事件
 */
function onNewButtonClick(event) {
  event.stopPropagation();
  showNewMenu(event.clientX, event.clientY);
}

/**
 * 排序按钮点击：显示下拉菜单。
 * @param {MouseEvent} event - 鼠标事件
 */
function onSortButtonClick(event) {
  event.stopPropagation();
  showSortMenu(event.clientX, event.clientY);
}

/**
 * 关闭预览模态框。
 */
function closePreview() {
  document.getElementById("preview-modal").classList.add("hidden");
  document.getElementById("preview-body").innerHTML = "";
}
