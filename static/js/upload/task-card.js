/**
 * 上传任务卡片渲染。
 *
 * 将任务状态、统计数据、进度条、速度曲线与操作按钮组合为一个卡片，
 * 供上传面板列表复用。
 */

import { createUploadIcon } from "./icons.js";
import { renderSpeedChart } from "./task-chart.js";
import { calculateMetrics, createStatsGrid } from "./task-stats.js";
import {
  getTaskKindLabel,
  isTaskOngoing,
  TASK_STATUS,
} from "./upload-status.js";

/**
 * 创建操作按钮。
 *
 * @param {string} action 操作标识。
 * @param {string} label 无障碍标签与提示。
 * @param {"pause"|"stop"|"play"} iconName 图标名称。
 * @returns {HTMLButtonElement} 按钮元素。
 */
function createActionButton(action, label, iconName) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button icon-button--small upload-task__action";
  button.dataset.uploadAction = action;
  button.title = label;
  button.setAttribute("aria-label", label);
  button.appendChild(createUploadIcon(iconName));
  return button;
}

/**
 * 创建任务操作区。
 *
 * @param {Object} task 上传任务。
 * @returns {HTMLElement} 操作区元素。
 */
function createTaskActions(task) {
  const container = document.createElement("div");
  container.className = "upload-task__actions";

  if (task.status === TASK_STATUS.PAUSED) {
    container.appendChild(createActionButton("resume", "继续", "play"));
  } else if (
    task.status === TASK_STATUS.UPLOADING ||
    task.status === TASK_STATUS.PENDING
  ) {
    container.appendChild(createActionButton("pause", "暂停", "pause"));
  }

  if (isTaskOngoing(task.status)) {
    container.appendChild(createActionButton("terminate", "终止", "stop"));
  }
  return container;
}

/**
 * 返回任务状态文案。
 *
 * @param {Object} task 上传任务。
 * @returns {string} 状态文案。
 */
function buildStatusText(task) {
  switch (task.status) {
    case TASK_STATUS.UPLOADING:
      return task.currentPhase || "正在上传…";
    case TASK_STATUS.PAUSED:
      return task.currentPhase
        ? `已暂停 · ${task.currentPhase.replace("正在上传：", "")}`
        : "已暂停";
    case TASK_STATUS.CONFLICT:
      return "检测到同名文件，等待处理";
    case TASK_STATUS.COMPLETED: {
      const parts = [`已完成：成功 ${task.completedFiles} 个文件`];
      if (task.skippedFiles > 0) {
        parts.push(`跳过 ${task.skippedFiles}`);
      }
      if (task.failedFiles > 0) {
        parts.push(`失败 ${task.failedFiles}`);
      }
      return parts.join("，");
    }
    case TASK_STATUS.FAILED:
      return `上传失败：${task.error?.message || "未知错误"}`;
    case TASK_STATUS.CANCELED:
      return "已终止上传";
    default:
      return "等待上传…";
  }
}

/**
 * 创建进度条。
 *
 * @param {Object} metrics 指标集合。
 * @returns {HTMLElement} 进度条元素。
 */
function createProgress(metrics) {
  const container = document.createElement("div");
  container.className = "upload-task__progress";
  const bar = document.createElement("div");
  bar.className = "upload-task__progress-bar";
  bar.style.width = `${Math.min(100, Math.max(0, metrics.percent))}%`;
  container.appendChild(bar);
  return container;
}

/**
 * 创建冲突处理区。
 *
 * @param {Object} task 上传任务。
 * @returns {HTMLElement} 冲突区元素。
 */
function createConflictPanel(task) {
  const panel = document.createElement("div");
  panel.className = "upload-task__conflict";

  const message = document.createElement("p");
  message.textContent = `目标位置已存在同名文件「${task.conflict.filename}」，任务已暂停。`;
  const actions = document.createElement("div");
  actions.className = "upload-task__conflict-actions";

  const skipButton = document.createElement("button");
  skipButton.type = "button";
  skipButton.className = "tool-button";
  skipButton.dataset.uploadAction = "conflict-skip";
  skipButton.textContent = "跳过";

  const replaceButton = document.createElement("button");
  replaceButton.type = "button";
  replaceButton.className = "tool-button primary";
  replaceButton.dataset.uploadAction = "conflict-replace";
  replaceButton.textContent = "替换";

  actions.append(skipButton, replaceButton);
  panel.append(message, actions);
  return panel;
}

/**
 * 创建单个上传任务卡片。
 *
 * @param {Object} task 上传任务。
 * @returns {HTMLElement} 任务卡片元素。
 */
export function createTaskCard(task) {
  const metrics = calculateMetrics(task, Date.now());
  const card = document.createElement("article");
  card.className = `upload-task upload-task--${task.status}`;
  card.dataset.taskId = task.id;
  card.dataset.taskStatus = task.status;

  const header = document.createElement("header");
  header.className = "upload-task__header";

  const title = document.createElement("div");
  title.className = "upload-task__title";
  const kind = document.createElement("span");
  kind.className = "upload-task__kind";
  kind.textContent = getTaskKindLabel(task.kind);
  const name = document.createElement("span");
  name.className = "upload-task__name";
  name.textContent = task.getDisplayName();
  name.title = task.targetDirectory;
  title.append(kind, name);
  header.append(title, createTaskActions(task));

  const status = document.createElement("div");
  status.className = "upload-task__status";
  status.textContent = buildStatusText(task);

  card.append(header, status);
  if (task.status === TASK_STATUS.CONFLICT && task.conflict) {
    card.appendChild(createConflictPanel(task));
  }
  card.append(
    createStatsGrid(task, metrics),
    createProgress(metrics),
    renderSpeedChart(task.speedTracker.getSamples())
  );
  return card;
}

/**
 * 更新卡片中的动态内容，保留操作按钮与冲突区域。
 *
 * 仅当任务状态未变化时可用；状态变化时应重新创建卡片。
 *
 * @param {HTMLElement} card 现有卡片。
 * @param {Object} task 上传任务。
 * @returns {boolean} 是否已更新。
 */
export function updateTaskCard(card, task) {
  if (card.dataset.taskStatus !== task.status) {
    return false;
  }

  const metrics = calculateMetrics(task, Date.now());
  const status = card.querySelector(".upload-task__status");
  if (status) {
    status.textContent = buildStatusText(task);
  }

  const stats = card.querySelector(".upload-task__stats");
  if (stats) {
    stats.replaceWith(createStatsGrid(task, metrics));
  }

  const bar = card.querySelector(".upload-task__progress-bar");
  if (bar) {
    bar.style.width = `${Math.min(100, Math.max(0, metrics.percent))}%`;
  }

  const chart = card.querySelector(".upload-task__chart");
  if (chart) {
    chart.replaceWith(renderSpeedChart(task.speedTracker.getSamples()));
  }
  return true;
}
