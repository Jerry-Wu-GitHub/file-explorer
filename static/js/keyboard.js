/**
 * 全局键盘快捷键。
 *
 * 支持的快捷键：
 *
 * - `Alt+N`：新开一个与当前 URL 相同的浏览器标签页；
 * - `Ctrl+Shift+N`：新建文件夹；
 * - `Ctrl+C`：复制选中条目；
 * - `Ctrl+X`：剪切选中条目；
 * - `Ctrl+V`：粘贴剪贴板内容；
 * - `Ctrl+F`：焦点到搜索栏。
 *
 * macOS 上同时支持 `Cmd` 键。文本输入区域（`input` / `textarea` /
 * `contenteditable`）内的 `Ctrl+C` / `Ctrl+X` / `Ctrl+V` 保持原生
 * 行为，不拦截。
 */

import { focusSearchInput } from "./path-bar.js";

/** 回调集合，由 `initializeKeyboard` 注入。 */
let callbacks = {
  onNewFolder: () => {},
  onCopy: () => {},
  onCut: () => {},
  onPaste: () => {},
};

/** 是否已初始化。 */
let initialized = false;

/**
 * 判断事件目标是否位于文本输入区域。
 *
 * @param {EventTarget|null} target 事件目标。
 * @returns {boolean} 是否为文本输入区域。
 */
function isTextInput(target) {
  if (!target || !(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  if (tagName === "input") {
    const type = (target.getAttribute("type") || "text").toLowerCase();
    return ![
      "checkbox",
      "radio",
      "button",
      "submit",
      "reset",
      "file",
      "image",
    ].includes(type);
  }
  if (tagName === "textarea") {
    return true;
  }
  return target.isContentEditable;
}

/**
 * 是否按下了修饰键（Ctrl 或 Cmd）。
 *
 * @param {KeyboardEvent} event 键盘事件。
 * @returns {boolean} 是否按下。
 */
function hasPrimaryModifier(event) {
  return event.ctrlKey || event.metaKey;
}

/**
 * 处理 `Alt+N`：新开一个与当前 URL 相同的标签页。
 *
 * @param {KeyboardEvent} event 键盘事件。
 * @returns {boolean} 是否已处理。
 */
function handleOpenNewTab(event) {
  if (!event.altKey || hasPrimaryModifier(event)) {
    return false;
  }
  if (event.key.toLowerCase() !== "n") {
    return false;
  }
  event.preventDefault();
  window.open(window.location.href, "_blank");
  return true;
}

/**
 * 处理 `Ctrl+Shift+N`：新建文件夹。
 *
 * @param {KeyboardEvent} event 键盘事件。
 * @returns {boolean} 是否已处理。
 */
function handleNewFolder(event) {
  if (!hasPrimaryModifier(event) || !event.shiftKey) {
    return false;
  }
  if (event.key.toLowerCase() !== "n") {
    return false;
  }
  event.preventDefault();
  callbacks.onNewFolder();
  return true;
}

/**
 * 处理 `Ctrl+C`：复制选中条目。
 *
 * @param {KeyboardEvent} event 键盘事件。
 * @returns {boolean} 是否已处理。
 */
function handleCopy(event) {
  if (!hasPrimaryModifier(event) || event.shiftKey || event.altKey) {
    return false;
  }
  if (event.key.toLowerCase() !== "c") {
    return false;
  }
  if (isTextInput(event.target)) {
    return false;
  }
  event.preventDefault();
  callbacks.onCopy();
  return true;
}

/**
 * 处理 `Ctrl+X`：剪切选中条目。
 *
 * @param {KeyboardEvent} event 键盘事件。
 * @returns {boolean} 是否已处理。
 */
function handleCut(event) {
  if (!hasPrimaryModifier(event) || event.shiftKey || event.altKey) {
    return false;
  }
  if (event.key.toLowerCase() !== "x") {
    return false;
  }
  if (isTextInput(event.target)) {
    return false;
  }
  event.preventDefault();
  callbacks.onCut();
  return true;
}

/**
 * 处理 `Ctrl+V`：粘贴剪贴板内容。
 *
 * @param {KeyboardEvent} event 键盘事件。
 * @returns {boolean} 是否已处理。
 */
function handlePaste(event) {
  if (!hasPrimaryModifier(event) || event.shiftKey || event.altKey) {
    return false;
  }
  if (event.key.toLowerCase() !== "v") {
    return false;
  }
  if (isTextInput(event.target)) {
    return false;
  }
  event.preventDefault();
  callbacks.onPaste();
  return true;
}

/**
 * 处理 `Ctrl+F`：焦点到搜索栏。
 *
 * @param {KeyboardEvent} event 键盘事件。
 * @returns {boolean} 是否已处理。
 */
function handleFocusSearch(event) {
  if (!hasPrimaryModifier(event) || event.shiftKey || event.altKey) {
    return false;
  }
  if (event.key.toLowerCase() !== "f") {
    return false;
  }
  event.preventDefault();
  focusSearchInput();
  return true;
}

/**
 * 键盘事件总入口。
 *
 * 按优先级依次尝试各个处理器，第一个命中的处理器负责 `preventDefault`。
 *
 * @param {KeyboardEvent} event 键盘事件。
 */
function handleKeyDown(event) {
  if (handleOpenNewTab(event)) return;
  if (handleNewFolder(event)) return;
  if (handleCopy(event)) return;
  if (handleCut(event)) return;
  if (handlePaste(event)) return;
  if (handleFocusSearch(event)) return;
}

/**
 * 初始化键盘快捷键。
 *
 * 应在 `main.js` 中调用一次并注入回调。
 *
 * @param {Object} [options] 回调集合。
 * @param {() => void} [options.onNewFolder] 新建文件夹。
 * @param {() => void} [options.onCopy] 复制选中。
 * @param {() => void} [options.onCut] 剪切选中。
 * @param {() => void} [options.onPaste] 粘贴。
 */
export function initializeKeyboard(options = {}) {
  if (initialized) {
    return;
  }
  initialized = true;
  callbacks = { ...callbacks, ...options };
  document.addEventListener("keydown", handleKeyDown);
}
