/**
 * 菜单模块：上下文菜单、新建下拉、排序下拉的构建与交互。
 */

import { executeAction } from "./actions.js";
import { reloadDirectory, state } from "./state.js";

/** 菜单 DOM 元素引用 */
const menuIds = ["context-menu", "new-menu", "sort-menu"];
const menus = {};

/** 菜单项 action 处理器 */
let actionHandler = executeAction;

/**
 * 缓存菜单 DOM 元素并绑定点击事件。
 */
export function initMenus() {
  for (const id of menuIds) {
    menus[id] = document.getElementById(id);
    menus[id].addEventListener("click", onMenuClick);
  }
}

/**
 * 显示上下文菜单。
 * @param {number} x - 屏幕横坐标
 * @param {number} y - 屏幕纵坐标
 * @param {object[]} items - 菜单项列表 {label, action, disabled}
 */
export function showContextMenu(x, y, items) {
  const menu = menus["context-menu"];
  menu.innerHTML = "";
  for (const item of items) {
    if (item.label === "-") {
      const separator = document.createElement("div");
      separator.className = "menu-separator";
      menu.appendChild(separator);
      continue;
    }
    const button = document.createElement("button");
    button.textContent = item.label;
    button.disabled = Boolean(item.disabled);
    button.dataset.action = item.action;
    menu.appendChild(button);
  }
  openMenu(menu, x, y);
}

/**
 * 显示新建下拉菜单。
 * @param {number} x - 屏幕横坐标
 * @param {number} y - 屏幕纵坐标
 */
export function showNewMenu(x, y) {
  const menu = menus["new-menu"];
  menu.innerHTML = "";
  const items = [
    { label: "文件夹", action: "newFolder" },
    { label: "文件", action: "newFile" },
    { label: "符号链接", action: "newLink" },
  ];
  for (const item of items) {
    const button = document.createElement("button");
    button.textContent = item.label;
    button.dataset.action = item.action;
    menu.appendChild(button);
  }
  openMenu(menu, x, y);
}

/**
 * 显示排序下拉菜单。
 * @param {number} x - 屏幕横坐标
 * @param {number} y - 屏幕纵坐标
 */
export function showSortMenu(x, y) {
  const menu = menus["sort-menu"];
  menu.innerHTML = "";
  const fields = [
    { label: "名称", value: "name" },
    { label: "大小", value: "size" },
    { label: "修改时间", value: "modifiedAt" },
    { label: "创建时间", value: "createdAt" },
    { label: "访问时间", value: "accessedAt" },
  ];
  for (const field of fields) {
    const button = document.createElement("button");
    const marker =
      state.sortField === field.value ? (state.sortDirection === "asc" ? " ↑" : " ↓") : "";
    button.textContent = field.label + marker;
    button.dataset.action = "setSort";
    button.dataset.field = field.value;
    menu.appendChild(button);
  }
  const reverseButton = document.createElement("button");
  reverseButton.textContent = state.sortDirection === "asc" ? "切换为降序" : "切换为升序";
  reverseButton.dataset.action = "reverseSort";
  menu.appendChild(reverseButton);
  openMenu(menu, x, y);
}

/**
 * 打开菜单并定位。
 * @param {HTMLElement} menu - 菜单元素
 * @param {number} x - 横坐标
 * @param {number} y - 纵坐标
 */
function openMenu(menu, x, y) {
  closeAllMenus();
  menu.classList.remove("hidden");
  const rect = menu.getBoundingClientRect();
  const left = Math.min(x, window.innerWidth - rect.width - 8);
  const top = Math.min(y, window.innerHeight - rect.height - 8);
  menu.style.left = `${Math.max(4, left)}px`;
  menu.style.top = `${Math.max(4, top)}px`;
}

/**
 * 关闭所有菜单。
 */
export function closeAllMenus() {
  for (const id of menuIds) {
    menus[id].classList.add("hidden");
  }
}

/**
 * 菜单点击分发。
 * @param {MouseEvent} event - 鼠标事件
 */
function onMenuClick(event) {
  const button = event.target.closest("button");
  if (!button || button.disabled) {
    return;
  }
  const action = button.dataset.action;
  const menuId = button.closest(".dropdown-menu, .context-menu")
    ? button.closest(".dropdown-menu, .context-menu").id
    : "";

  if (menuId === "context-menu" && action === "sortMenu") {
    closeAllMenus();
    showSortMenu(event.clientX, event.clientY);
    return;
  }
  if (menuId === "context-menu" && action === "newMenu") {
    closeAllMenus();
    showNewMenu(event.clientX, event.clientY);
    return;
  }
  if (action === "setSort") {
    state.sortField = button.dataset.field;
    state.page = 1;
    closeAllMenus();
    reloadDirectory();
    return;
  }
  if (action === "reverseSort") {
    state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
    state.page = 1;
    closeAllMenus();
    reloadDirectory();
    return;
  }
  closeAllMenus();
  actionHandler(action);
}
