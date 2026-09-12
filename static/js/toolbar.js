/**
 * 工具栏交互。
 *
 * 负责：
 *
 * - 绑定按钮点击并派发到回调；
 * - 根据状态快照更新按钮禁用态；
 * - 新建与排序下拉菜单的显示与选项处理；
 * - 上传按钮的临时菜单（选择文件 / 选择文件夹）。
 *
 * 工具栏不直接调用 API；具体操作交由 `main.js` 通过回调完成。
 */

import { hideDropdown, showDropdown, toggleDropdown } from "./dropdown.js";
import { setShowHidden, setSort } from "./state.js";

/** 回调集合，由 `initializeToolbar` 注入。 */
let callbacks = {
  onNewFolder: () => {},
  onNewFile: () => {},
  onNewSymlink: () => {},
  onCut: () => {},
  onCopy: () => {},
  onPaste: () => {},
  onDownload: () => {},
  onDownloadZip: () => {},
  onUploadFiles: () => {},
  onUploadFolder: () => {},
  onRename: () => {},
  onShare: () => {},
  onDelete: () => {},
  onSort: () => {},
  onShowHiddenChange: () => {},
};

/** 是否已初始化。 */
let initialized = false;

/** 上传按钮动态创建的菜单引用。 */
let uploadMenu = null;

/**
 * 绑定一个简单的无状态下拉按钮。
 *
 * @param {string} buttonId 按钮 ID。
 * @param {string} menuId 菜单 ID。
 */
function bindDropdownButton(buttonId, menuId) {
  const button = document.getElementById(buttonId);
  const menu = document.getElementById(menuId);
  if (!button || !menu) {
    return;
  }
  button.addEventListener("click", () => toggleDropdown(menu, button));
}

/**
 * 绑定一个简单按钮的点击回调。
 *
 * @param {string} buttonId 按钮 ID。
 * @param {() => void} handler 回调。
 */
function bindSimpleButton(buttonId, handler) {
  document.getElementById(buttonId)?.addEventListener("click", () => {
    handler();
  });
}

/**
 * 处理新建菜单点击。
 *
 * @param {MouseEvent} event 点击事件。
 */
function handleNewMenuClick(event) {
  const button = event.target.closest("button[data-menu-action]");
  if (!button) {
    return;
  }
  const menu = document.getElementById("new-menu");
  if (menu) {
    hideDropdown(menu);
  }
  const action = button.dataset.menuAction;
  if (action === "new-folder") {
    callbacks.onNewFolder();
  } else if (action === "new-file") {
    callbacks.onNewFile();
  } else if (action === "new-symlink") {
    callbacks.onNewSymlink();
  }
}

/**
 * 处理排序菜单点击。
 *
 * @param {MouseEvent} event 点击事件。
 */
function handleSortMenuClick(event) {
  const button = event.target.closest("button[data-sort-field]");
  if (!button) {
    return;
  }
  const menu = document.getElementById("sort-menu");
  if (menu) {
    hideDropdown(menu);
  }
  const field = button.dataset.sortField;
  const direction = button.dataset.sortDirection === "desc" ? "desc" : "asc";
  setSort(field, direction);
  callbacks.onSort(field, direction);
}

/**
 * 创建上传按钮的临时菜单。
 *
 * @returns {HTMLElement} 菜单元素。
 */
function createUploadMenu() {
  const menu = document.createElement("div");
  menu.className = "dropdown-menu";
  const filesButton = document.createElement("button");
  filesButton.type = "button";
  filesButton.dataset.uploadKind = "files";
  filesButton.textContent = "选择文件";
  const folderButton = document.createElement("button");
  folderButton.type = "button";
  folderButton.dataset.uploadKind = "folder";
  folderButton.textContent = "选择文件夹";
  menu.append(filesButton, folderButton);
  return menu;
}

/**
 * 清理上传按钮的临时菜单。
 */
function disposeUploadMenu() {
  if (!uploadMenu) {
    return;
  }
  hideDropdown(uploadMenu);
  uploadMenu.remove();
  uploadMenu = null;
}

/**
 * 处理上传菜单点击。
 *
 * @param {MouseEvent} event 点击事件。
 */
function handleUploadMenuClick(event) {
  const button = event.target.closest("button[data-upload-kind]");
  if (!button) {
    return;
  }
  const kind = button.dataset.uploadKind;
  disposeUploadMenu();
  if (kind === "folder") {
    callbacks.onUploadFolder();
  } else {
    callbacks.onUploadFiles();
  }
}

/**
 * 处理上传按钮点击：切换临时菜单。
 *
 * @param {MouseEvent} event 点击事件。
 */
function handleUploadButtonClick(event) {
  disposeUploadMenu();
  uploadMenu = createUploadMenu();
  document.body.appendChild(uploadMenu);
  showDropdown(uploadMenu, event.currentTarget);
  uploadMenu.addEventListener("click", handleUploadMenuClick);
}

/**
 * 初始化工具栏。
 *
 * 应在 `main.js` 中调用一次，并注入所有操作回调。
 *
 * @param {Object} [options] 回调集合。
 */
export function initializeToolbar(options = {}) {
  if (initialized) {
    return;
  }
  initialized = true;
  callbacks = { ...callbacks, ...options };

  bindDropdownButton("new-button", "new-menu");
  bindDropdownButton("sort-button", "sort-menu");

  bindSimpleButton("cut-button", callbacks.onCut);
  bindSimpleButton("copy-button", callbacks.onCopy);
  bindSimpleButton("download-button", callbacks.onDownload);
  bindSimpleButton("download-zip-button", callbacks.onDownloadZip);
  bindSimpleButton("paste-button", callbacks.onPaste);
  bindSimpleButton("rename-button", callbacks.onRename);
  bindSimpleButton("share-button", callbacks.onShare);
  bindSimpleButton("delete-button", callbacks.onDelete);

  document
    .getElementById("new-menu")
    ?.addEventListener("click", handleNewMenuClick);
  document
    .getElementById("sort-menu")
    ?.addEventListener("click", handleSortMenuClick);

  document
    .getElementById("upload-button")
    ?.addEventListener("click", handleUploadButtonClick);

  const showHiddenCheckbox = document.getElementById("show-hidden-checkbox");
  showHiddenCheckbox?.addEventListener("change", (event) => {
    setShowHidden(event.target.checked);
    callbacks.onShowHiddenChange(event.target.checked);
  });
}

/**
 * 按 ID 设置按钮禁用态。
 *
 * @param {string} buttonId 按钮 ID。
 * @param {boolean} disabled 是否禁用。
 */
function setButtonDisabled(buttonId, disabled) {
  const element = document.getElementById(buttonId);
  if (element) {
    element.disabled = disabled;
  }
}

/**
 * 根据状态快照更新工具栏按钮禁用态与勾选状态。
 *
 * @param {Object} state 状态快照。
 */
export function renderToolbar(state) {
  const hasSelection = state.selectedPaths.length > 0;
  const hasSingleSelection = state.selectedPaths.length === 1;
  const hasClipboard =
    state.clipboard !== null && state.clipboard.paths.length > 0;

  setButtonDisabled("cut-button", !hasSelection);
  setButtonDisabled("copy-button", !hasSelection);
  setButtonDisabled("download-button", !hasSelection);
  setButtonDisabled("download-zip-button", !hasSelection);
  setButtonDisabled("paste-button", !hasClipboard);
  setButtonDisabled("rename-button", !hasSingleSelection);
  setButtonDisabled("share-button", !hasSingleSelection);
  setButtonDisabled("delete-button", !hasSelection);

  const showHiddenCheckbox = document.getElementById("show-hidden-checkbox");
  if (showHiddenCheckbox) {
    showHiddenCheckbox.checked = state.showHidden;
  }
}

/**
 * 关闭上传按钮的临时菜单。供外部（例如按下 Escape）调用。
 */
export function closeUploadMenu() {
  disposeUploadMenu();
}
