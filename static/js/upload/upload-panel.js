/**
 * 上传任务面板。
 *
 * 展示所有上传任务，绑定暂停、继续、终止与冲突处理操作，并维护
 * 状态栏上传图标的进行中数量徽标与动画状态。
 */

import { createTaskCard, updateTaskCard } from "./task-card.js";
import {
  configureUploadManager,
  getActiveUploadTaskCount,
  getUploadTasks,
  initializeUploadManager,
  pauseUploadTaskById,
  requestTerminateUploadTask,
  resolveUploadTaskConflict,
  resumeUploadTaskById,
} from "./upload-manager.js";

/** 是否已初始化。 */
let initialized = false;

/**
 * 获取面板元素。
 *
 * @returns {HTMLElement|null} 面板元素。
 */
function getPanel() {
  return document.getElementById("upload-panel");
}

/**
 * 返回面板是否可见。
 *
 * @returns {boolean} 是否可见。
 */
function isPanelVisible() {
  const panel = getPanel();
  return Boolean(panel && !panel.classList.contains("hidden"));
}

/**
 * 更新状态栏图标徽标与动画。
 *
 * @param {number} activeCount 进行中任务数量。
 */
function renderBadge(activeCount) {
  const button = document.getElementById("upload-status-button");
  const badge = document.getElementById("upload-task-badge");
  if (!button || !badge) {
    return;
  }
  badge.textContent = activeCount > 99 ? "99+" : `${activeCount}`;
  badge.classList.toggle("hidden", activeCount === 0);
  button.classList.toggle("is-active", activeCount > 0);
  button.setAttribute(
    "aria-label",
    activeCount > 0 ? `上传任务，${activeCount} 个进行中` : "上传任务"
  );
}

/**
 * 渲染任务列表。
 *
 * @param {Object[]} tasks 任务列表。
 */
function renderTaskList(tasks) {
  const list = document.getElementById("upload-task-list");
  const emptyHint = document.getElementById("upload-empty-hint");
  const countLabel = document.getElementById("upload-panel-count");
  if (!list || !emptyHint) {
    return;
  }

  const activeCount = getActiveUploadTaskCount();
  if (countLabel) {
    countLabel.textContent =
      activeCount > 0 ? `上传任务（${activeCount} 个进行中）` : "上传任务";
  }

  if (tasks.length === 0) {
    list.replaceChildren();
    emptyHint.classList.remove("hidden");
    return;
  }
  emptyHint.classList.add("hidden");

  const existingCards = [...list.children];
  const sameOrder =
    existingCards.length === tasks.length &&
    tasks.every(
      (task, index) => existingCards[index].dataset.taskId === task.id
    );

  if (sameOrder) {
    tasks.forEach((task, index) => {
      const card = existingCards[index];
      if (!updateTaskCard(card, task)) {
        card.replaceWith(createTaskCard(task));
      }
    });
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const task of tasks) {
    fragment.appendChild(createTaskCard(task));
  }
  list.replaceChildren(fragment);
}

/**
 * 处理任务集合变化。
 *
 * @param {Object[]} tasks 任务列表。
 */
function handleTasksChanged(tasks) {
  renderBadge(getActiveUploadTaskCount());
  if (isPanelVisible()) {
    renderTaskList(tasks);
  }
}

/**
 * 打开上传面板。
 */
export function openUploadPanel() {
  const panel = getPanel();
  const button = document.getElementById("upload-status-button");
  if (!panel) {
    return;
  }
  panel.classList.remove("hidden");
  button?.setAttribute("aria-expanded", "true");
  renderTaskList(getUploadTasks());
}

/**
 * 关闭上传面板。
 */
export function closeUploadPanel() {
  const panel = getPanel();
  const button = document.getElementById("upload-status-button");
  panel?.classList.add("hidden");
  button?.setAttribute("aria-expanded", "false");
}

/**
 * 切换上传面板显示状态。
 */
function toggleUploadPanel() {
  if (isPanelVisible()) {
    closeUploadPanel();
  } else {
    openUploadPanel();
  }
}

/**
 * 处理任务列表中的操作按钮点击。
 *
 * @param {MouseEvent} event 点击事件。
 */
function handleTaskListClick(event) {
  const button = event.target.closest("button[data-upload-action]");
  if (!button) {
    return;
  }
  const card = button.closest("[data-task-id]");
  const taskId = card?.dataset.taskId;
  if (!taskId) {
    return;
  }

  switch (button.dataset.uploadAction) {
    case "pause":
      pauseUploadTaskById(taskId);
      break;
    case "resume":
      resumeUploadTaskById(taskId);
      break;
    case "terminate":
      requestTerminateUploadTask(taskId);
      break;
    case "conflict-skip":
      resolveUploadTaskConflict(taskId, "skip");
      break;
    case "conflict-replace":
      resolveUploadTaskConflict(taskId, "replace");
      break;
    default:
      break;
  }
}

/**
 * 处理面板外点击。
 *
 * @param {MouseEvent} event 点击事件。
 */
function handleDocumentClick(event) {
  if (!isPanelVisible()) {
    return;
  }
  const panel = getPanel();
  const button = document.getElementById("upload-status-button");
  const confirmModal = document.getElementById("confirm-modal");
  const path = typeof event.composedPath === "function"
    ? event.composedPath()
    : [];
  if (
    (panel && (path.includes(panel) || panel.contains(event.target))) ||
    (button && (path.includes(button) || button.contains(event.target))) ||
    (confirmModal &&
      (path.includes(confirmModal) || confirmModal.contains(event.target)))
  ) {
    return;
  }
  closeUploadPanel();
}

/**
 * 处理 Escape 键。
 *
 * @param {KeyboardEvent} event 键盘事件。
 */
function handleKeydown(event) {
  if (event.key !== "Escape" || !isPanelVisible()) {
    return;
  }
  const confirmModal = document.getElementById("confirm-modal");
  if (confirmModal && !confirmModal.classList.contains("hidden")) {
    return;
  }
  closeUploadPanel();
}

/**
 * 初始化上传面板。
 */
export function initializeUploadPanel() {
  if (initialized) {
    return;
  }
  initialized = true;

  document
    .getElementById("upload-status-button")
    ?.addEventListener("click", toggleUploadPanel);
  document
    .getElementById("upload-panel-close-button")
    ?.addEventListener("click", closeUploadPanel);
  document
    .getElementById("upload-task-list")
    ?.addEventListener("click", handleTaskListClick);
  document.addEventListener("click", handleDocumentClick);
  document.addEventListener("keydown", handleKeydown);

  configureUploadManager({
    onTasksChanged: handleTasksChanged,
    onRequestOpenPanel: openUploadPanel,
  });
  initializeUploadManager();
  renderBadge(0);
  renderTaskList([]);
}
