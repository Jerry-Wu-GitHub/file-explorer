/**
 * 选择交互：网格单击/双击/右键与选择状态管理。
 */

import { getMetadata } from "./api.js";
import { getElement } from "./dom.js";
import { showContextMenu } from "./menus.js";
import { navigateToPath } from "./navigation.js";
import { previewEntry } from "./preview.js";
import { refreshToolbar, state } from "./state.js";

/**
 * 绑定网格选择相关事件。
 */
export function initSelection() {
  getElement("file-grid").addEventListener("click", onGridClick);
  getElement("file-grid").addEventListener("dblclick", onGridDoubleClick);
  getElement("file-grid").addEventListener("contextmenu", onGridContextMenu);
}

/**
 * 网格单击：处理选择。
 * @param {MouseEvent} event - 鼠标事件
 */
function onGridClick(event) {
  const item = event.target.closest(".file-item");
  if (!item) {
    return;
  }
  if (event.ctrlKey || event.metaKey) {
    toggleItemSelection(item);
  } else {
    clearSelection();
    selectItem(item);
  }
}

/**
 * 网格双击：目录进入，文件预览或下载。
 * @param {MouseEvent} event - 鼠标事件
 */
function onGridDoubleClick(event) {
  const item = event.target.closest(".file-item");
  if (!item) {
    return;
  }
  const path = item.dataset.path;
  const type = item.dataset.type;
  if (type === "directory") {
    navigateToPath(path);
    return;
  }
  if (type === "link") {
    handleLinkDoubleClick(path);
    return;
  }
  previewEntry(path);
}

/**
 * 网格右键：条目上或空白处显示对应菜单。
 * @param {MouseEvent} event - 鼠标事件
 */
function onGridContextMenu(event) {
  event.preventDefault();
  const item = event.target.closest(".file-item");
  if (item) {
    if (!item.classList.contains("selected")) {
      clearSelection();
      selectItem(item);
    }
    showContextMenu(event.clientX, event.clientY, buildEntryMenu());
  } else {
    showContextMenu(event.clientX, event.clientY, buildBlankMenu());
  }
}

/**
 * 处理链接双击：跟随链接进入目录或预览文件。
 * @param {string} path - 链接路径
 */
async function handleLinkDoubleClick(path) {
  try {
    const result = await getMetadata(path);
    if (result.data && result.data.type === "directory") {
      navigateToPath(path);
    } else {
      previewEntry(path);
    }
  } catch (error) {
    alert(`无法访问链接：${error.message}`);
  }
}

/**
 * 切换单个条目选中状态。
 * @param {HTMLElement} item - 条目元素
 */
function toggleItemSelection(item) {
  if (item.classList.contains("selected")) {
    item.classList.remove("selected");
    state.selection.delete(item.dataset.path);
  } else {
    item.classList.add("selected");
    state.selection.set(item.dataset.path, item);
  }
  refreshToolbar();
}

/**
 * 清除全部选择。
 */
function clearSelection() {
  state.selection.clear();
  for (const item of getElement("file-grid").querySelectorAll(".file-item.selected")) {
    item.classList.remove("selected");
  }
  refreshToolbar();
}

/**
 * 选中单个条目。
 * @param {HTMLElement} item - 条目元素
 */
function selectItem(item) {
  item.classList.add("selected");
  state.selection.set(item.dataset.path, item);
  refreshToolbar();
}

/**
 * 构建条目右键菜单项列表。
 * @returns {object[]} 菜单项
 */
function buildEntryMenu() {
  const selectedCount = state.selection.size;
  return [
    { label: "剪切", action: "cut" },
    { label: "复制", action: "copy" },
    { label: "下载", action: "download" },
    { label: "下载压缩包", action: "downloadZip", disabled: selectedCount < 2 },
    { label: "删除", action: "delete" },
    { label: "重命名", action: "rename", disabled: selectedCount !== 1 },
    { label: "属性", action: "properties" },
  ];
}

/**
 * 构建空白区域右键菜单项列表。
 * @returns {object[]} 菜单项
 */
function buildBlankMenu() {
  return [
    { label: "刷新", action: "refresh" },
    { label: "排序方式", action: "sortMenu" },
    { label: "粘贴", action: "paste", disabled: state.clipboard === null },
    { label: "新建", action: "newMenu" },
    { label: "属性", action: "folderProperties" },
  ];
}
