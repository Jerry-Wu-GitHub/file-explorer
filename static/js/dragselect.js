/**
 * 拖拽框选：在网格空白处按下并拖动，批量选中相交条目。
 */

import { refreshToolbar, state } from "./state.js";

/** 框选运行状态 */
const dragState = { active: false, startX: 0, startY: 0, box: null };

/** 网格元素引用 */
let gridElement = null;

/**
 * 初始化拖拽框选。
 * @param {HTMLElement} grid - 文件网格元素
 */
export function initDragSelect(grid) {
  gridElement = grid;
  grid.addEventListener("mousedown", onGridMouseDown);
  document.addEventListener("mousemove", onDocumentMouseMove);
  document.addEventListener("mouseup", onDocumentMouseUp);
}

/**
 * 网格空白处按下：启动框选。
 * @param {MouseEvent} event - 鼠标事件
 */
function onGridMouseDown(event) {
  if (event.button !== 0) {
    return;
  }
  if (event.target.closest(".file-item")) {
    return;
  }
  if (!event.ctrlKey && !event.metaKey) {
    clearAllSelection();
  }
  dragState.active = true;
  dragState.startX = event.clientX;
  dragState.startY = event.clientY;
  dragState.box = document.createElement("div");
  dragState.box.style.cssText =
    "position:fixed;border:1px solid var(--selection-border);" +
    "background:var(--selection-bg);z-index:90;pointer-events:none;";
  document.body.appendChild(dragState.box);
}

/**
 * 拖动过程中更新框选范围并同步选中状态。
 * @param {MouseEvent} event - 鼠标事件
 */
function onDocumentMouseMove(event) {
  if (!dragState.active || dragState.box === null) {
    return;
  }
  const left = Math.min(event.clientX, dragState.startX);
  const top = Math.min(event.clientY, dragState.startY);
  const width = Math.abs(event.clientX - dragState.startX);
  const height = Math.abs(event.clientY - dragState.startY);
  Object.assign(dragState.box.style, {
    left: `${left}px`,
    top: `${top}px`,
    width: `${width}px`,
    height: `${height}px`,
  });

  const boxRect = { left, top, right: left + width, bottom: top + height };
  for (const item of gridElement.querySelectorAll(".file-item")) {
    const itemRect = item.getBoundingClientRect();
    const intersects = !(
      itemRect.right < boxRect.left ||
      itemRect.left > boxRect.right ||
      itemRect.bottom < boxRect.top ||
      itemRect.top > boxRect.bottom
    );
    item.classList.toggle("selected", intersects);
    setSelectionState(item, intersects);
  }
}

/**
 * 鼠标松开结束框选。
 */
function onDocumentMouseUp() {
  if (!dragState.active) {
    return;
  }
  dragState.active = false;
  if (dragState.box) {
    dragState.box.remove();
    dragState.box = null;
  }
  refreshToolbar();
}

/**
 * 按选中状态同步选择集合。
 * @param {HTMLElement} item - 条目元素
 * @param {boolean} selected - 是否选中
 */
function setSelectionState(item, selected) {
  if (selected) {
    state.selection.set(item.dataset.path, item);
  } else {
    state.selection.delete(item.dataset.path);
  }
}

/**
 * 清除全部选择。
 */
function clearAllSelection() {
  state.selection.clear();
  for (const item of gridElement.querySelectorAll(".file-item.selected")) {
    item.classList.remove("selected");
  }
}
