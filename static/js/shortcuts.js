/**
 * 全局快捷键绑定。
 *
 * - Alt+N：新开一个与当前 URL 相同的浏览器页面
 * - Ctrl+Shift+N：新建文件夹
 * - Ctrl+C / Ctrl+X / Ctrl+V：复制 / 剪切 / 粘贴
 * - Ctrl+F：焦点到搜索栏
 * - Delete：删除选中；F2：重命名
 */

import { executeAction } from "./actions.js";

/** 搜索输入框元素 */
let searchInputElement = null;

/**
 * 绑定全局快捷键。
 * @param {HTMLElement} searchInput - 搜索输入框
 */
export function bindShortcuts(searchInput) {
  searchInputElement = searchInput;
  document.addEventListener("keydown", onGlobalKeydown);
}

/**
 * 全局键盘事件处理。
 * @param {KeyboardEvent} event - 键盘事件
 */
function onGlobalKeydown(event) {
  const target = event.target;
  const isTyping = target.tagName === "INPUT" || target.tagName === "TEXTAREA";

  if (event.altKey && event.key.toLowerCase() === "n") {
    event.preventDefault();
    window.open(window.location.href, "_blank");
    return;
  }
  if (event.ctrlKey && event.shiftKey && event.key.toUpperCase() === "N") {
    event.preventDefault();
    executeAction("newFolder");
    return;
  }
  if (isTyping) {
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "c") {
    executeAction("copy");
  } else if (event.ctrlKey && event.key.toLowerCase() === "x") {
    executeAction("cut");
  } else if (event.ctrlKey && event.key.toLowerCase() === "v") {
    executeAction("paste");
  } else if (event.ctrlKey && event.key.toLowerCase() === "f") {
    event.preventDefault();
    searchInputElement.focus();
    searchInputElement.select();
  } else if (event.key === "Delete") {
    executeAction("delete");
  } else if (event.key === "F2") {
    executeAction("rename");
  }
}
