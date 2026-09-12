/**
 * 文件列表的框选交互。
 *
 * 在文件列表容器空白处按下鼠标左键并拖拽时，显示选择框并实时
 * 更新选中集合。框选模式由按下瞬间的修饰键决定：
 *
 * - 不按修饰键：替换模式，仅保留框选范围内的条目；
 * - 按住 Ctrl / Cmd / Shift：增量模式，在原有选中基础上追加。
 *
 * 若用户仅点击空白处而不拖拽，交由 `file-list.js` 的空白点击处
 * 理器清空选中，本模块不重复处理。
 *
 * 实际拖拽发生框选后，浏览器仍会在 mouseup 之后派发一次 click
 * 事件。该 click 会落在空白区并触发 file-list 的 onBlankClick，
 * 从而清除刚框选出的选中。本模块通过在捕获阶段拦截一次 click
 * 来避免这一副作用。
 */

import { getState, setSelection } from "./state.js";

/** 判定为「拖拽」而非「点击」的最小位移（像素）。 */
const MIN_DRAG_PIXELS = 4;

/** 是否已初始化。 */
let initialized = false;

/** 是否正在进行框选。 */
let isBoxSelecting = false;

/** 是否已至少完成过一次带拖拽的框选。 */
let hasActuallyBoxSelected = false;

/** 是否应抑制下一次 click。 */
let suppressNextClick = false;

/** 本次框选是否为增量模式（保留开始时的选中集合）。 */
let isAdditiveSelection = false;

/** 框选开始时的客户端坐标。 */
let startClientX = 0;
let startClientY = 0;

/** 框选开始时的选中集合；替换模式下为空数组。 */
let initialSelection = [];

/**
 * 获取文件列表容器。
 *
 * @returns {HTMLElement|null} 容器元素。
 */
function getContainer() {
  return document.getElementById("file-list-container");
}

/**
 * 获取选择框元素。
 *
 * @returns {HTMLElement|null} 选择框元素。
 */
function getSelectionBox() {
  return document.getElementById("selection-box");
}

/**
 * 判断两个矩形是否相交。
 *
 * @param {DOMRect} a 矩形 A。
 * @param {DOMRect} b 矩形 B。
 * @returns {boolean} 是否相交。
 */
function rectanglesOverlap(a, b) {
  return (
    a.left < b.right &&
    a.right > b.left &&
    a.top < b.bottom &&
    a.bottom > b.top
  );
}

/**
 * 更新选择框的尺寸与位置。
 *
 * 使用 `position: fixed` 与视口坐标，避免受容器滚动影响。
 *
 * @param {HTMLElement} box 选择框元素。
 * @param {number} currentClientX 当前鼠标 X 坐标。
 * @param {number} currentClientY 当前鼠标 Y 坐标。
 */
function updateBoxElement(box, currentClientX, currentClientY) {
  const left = Math.min(startClientX, currentClientX);
  const top = Math.min(startClientY, currentClientY);
  const width = Math.abs(currentClientX - startClientX);
  const height = Math.abs(currentClientY - startClientY);

  box.style.position = "fixed";
  box.style.left = `${left}px`;
  box.style.top = `${top}px`;
  box.style.width = `${width}px`;
  box.style.height = `${height}px`;
}

/**
 * 根据选择框的位置更新选中集合。
 *
 * @param {DOMRect} boxRect 选择框矩形。
 */
function updateSelectionFromBox(boxRect) {
  const container = getContainer();
  if (!container) {
    return;
  }

  const merged = new Set(initialSelection);
  const entryElements = container.querySelectorAll(".file-item");
  for (const element of entryElements) {
    const elementRect = element.getBoundingClientRect();
    if (rectanglesOverlap(boxRect, elementRect)) {
      const path = element.dataset.path;
      if (path) {
        merged.add(path);
      }
    }
  }
  setSelection([...merged]);
}

/**
 * 处理鼠标按下：可能开始一次框选。
 *
 * 修饰键在按下瞬间决定本次框选是替换还是增量，与主流文件管理器
 * 一致；拖拽过程中改变修饰键不会切换模式。
 *
 * @param {MouseEvent} event 鼠标事件。
 */
function handleMouseDown(event) {
  if (event.button !== 0) {
    return;
  }
  if (event.target.closest(".file-item")) {
    return;
  }
  if (event.target.closest("input, textarea, button, select, a")) {
    return;
  }
  const container = getContainer();
  if (!container || !container.contains(event.target)) {
    return;
  }

  event.preventDefault();
  isBoxSelecting = false;
  hasActuallyBoxSelected = false;
  isAdditiveSelection =
    event.ctrlKey || event.metaKey || event.shiftKey;
  startClientX = event.clientX;
  startClientY = event.clientY;
  initialSelection = isAdditiveSelection
    ? [...getState().selectedPaths]
    : [];

  document.addEventListener("mousemove", handleMouseMove);
  document.addEventListener("mouseup", handleMouseUp);
}

/**
 * 处理鼠标移动：达到拖拽阈值后开始更新选择框。
 *
 * @param {MouseEvent} event 鼠标事件。
 */
function handleMouseMove(event) {
  const deltaX = Math.abs(event.clientX - startClientX);
  const deltaY = Math.abs(event.clientY - startClientY);

  if (!isBoxSelecting) {
    if (deltaX < MIN_DRAG_PIXELS && deltaY < MIN_DRAG_PIXELS) {
      return;
    }
    isBoxSelecting = true;
    hasActuallyBoxSelected = true;
    const box = getSelectionBox();
    if (box) {
      box.hidden = false;
    }
  }

  const box = getSelectionBox();
  if (!box) {
    return;
  }
  updateBoxElement(box, event.clientX, event.clientY);
  updateSelectionFromBox(box.getBoundingClientRect());
}

/**
 * 处理鼠标松开：隐藏选择框并清理监听。
 *
 * @param {MouseEvent} event 鼠标事件。
 */
function handleMouseUp(event) {
  document.removeEventListener("mousemove", handleMouseMove);
  document.removeEventListener("mouseup", handleMouseUp);

  const box = getSelectionBox();
  if (box) {
    box.hidden = true;
    box.style.left = "";
    box.style.top = "";
    box.style.width = "";
    box.style.height = "";
  }

  if (hasActuallyBoxSelected) {
    suppressNextClick = true;
    event.preventDefault();
    event.stopPropagation();
  }

  isBoxSelecting = false;
  hasActuallyBoxSelected = false;
  isAdditiveSelection = false;
  initialSelection = [];
}

/**
 * 捕获阶段拦截一次 click。
 *
 * 若刚刚完成过一次带拖拽的框选，则吞掉紧随其后的 click，避免
 * file-list 的空白点击处理器清空刚框选出的选中。
 *
 * @param {MouseEvent} event 点击事件。
 */
function handleCaptureClick(event) {
  if (!suppressNextClick) {
    return;
  }
  suppressNextClick = false;
  event.stopPropagation();
  event.preventDefault();
}

/**
 * 初始化框选交互。
 *
 * 应在 `main.js` 中调用一次。
 */
export function initializeSelection() {
  if (initialized) {
    return;
  }
  initialized = true;
  document.addEventListener("mousedown", handleMouseDown);
  document.addEventListener("click", handleCaptureClick, true);
}
