/**
 * 上传任务管理器。
 *
 * 创建并保存所有上传任务，负责定时采样速度、维护进行中任务数量、
 * 调用调度器执行暂停 / 继续 / 终止，以及在任务结束后刷新列表。
 */

import { CHUNKED_UPLOAD_THRESHOLD } from "../config.js";
import {
  extractErrorMessage,
  showError,
  showInfo,
  showSuccess,
} from "../toast.js";
import { showConfirmDialog } from "./confirm-dialog.js";
import { UploadTask } from "./upload-task.js";
import {
  isTaskOngoing,
  TASK_KIND,
  TASK_STATUS,
} from "./upload-status.js";
import {
  pauseUploadTask,
  resolveTaskConflict,
  resumeUploadTask,
  startUploadTask,
  terminateUploadTask,
} from "./task-runner.js";

/** 速度采样与面板刷新周期（毫秒）。 */
const TICK_INTERVAL_MILLISECONDS = 500;

/** 任务完成或结束后的保留时长（毫秒）。 */
const COMPLETED_REMOVE_DELAY = 5000;
const FINISHED_REMOVE_DELAY = 3000;

/** @type {UploadTask[]} */
let tasks = [];

/** @type {number|null} */
let tickTimer = null;

/** 外部回调。 */
let callbacks = {
  onTasksChanged: () => {},
  onRequestOpenPanel: () => {},
  onRefresh: () => {},
};

/**
 * 配置管理器回调。
 *
 * @param {Object} options 回调集合。
 * @param {(tasks: UploadTask[]) => void} [options.onTasksChanged] 任务变化回调。
 * @param {() => void} [options.onRequestOpenPanel] 请求打开面板。
 * @param {() => void} [options.onRefresh] 上传成功后的刷新回调。
 */
export function configureUploadManager(options = {}) {
  callbacks = { ...callbacks, ...options };
}

/**
 * 根据条目推断任务类型。
 *
 * @param {Array<{file: File, relativePath: string}>} entries 条目。
 * @returns {string} 任务类型。
 */
function classifyTask(entries) {
  const hasDirectoryPath = entries.some((entry) =>
    entry.relativePath.includes("/")
  );
  if (entries.length > 1 || hasDirectoryPath) {
    return TASK_KIND.BATCH;
  }
  return entries[0].file.size >= CHUNKED_UPLOAD_THRESHOLD
    ? TASK_KIND.SINGLE_CHUNKED
    : TASK_KIND.SINGLE;
}

/**
 * 通知界面任务集合发生变化。
 */
function notifyTasksChanged() {
  callbacks.onTasksChanged(tasks.slice());
}

/**
 * 查找任务。
 *
 * @param {string} taskId 任务 ID。
 * @returns {UploadTask|undefined} 任务。
 */
export function findUploadTask(taskId) {
  return tasks.find((task) => task.id === taskId);
}

/**
 * 返回当前任务快照。
 *
 * @returns {UploadTask[]} 任务列表副本。
 */
export function getUploadTasks() {
  return tasks.slice();
}

/**
 * 返回进行中任务数量。
 *
 * @returns {number} 数量。
 */
export function getActiveUploadTaskCount() {
  return tasks.filter((task) => isTaskOngoing(task.status)).length;
}

/**
 * 从列表中移除任务。
 *
 * @param {string} taskId 任务 ID。
 */
function removeTask(taskId) {
  tasks = tasks.filter((task) => task.id !== taskId);
  notifyTasksChanged();
}

/**
 * 安排任务从面板中移除。
 *
 * @param {UploadTask} task 上传任务。
 */
function scheduleTaskRemoval(task) {
  const delay =
    task.status === TASK_STATUS.COMPLETED
      ? COMPLETED_REMOVE_DELAY
      : FINISHED_REMOVE_DELAY;
  window.setTimeout(() => removeTask(task.id), delay);
}

/**
 * 构造任务结束提示文案。
 *
 * @param {UploadTask} task 上传任务。
 * @returns {string} 提示文案。
 */
function buildFinishedMessage(task) {
  const parts = [`成功 ${task.completedFiles}`];
  if (task.skippedFiles > 0) {
    parts.push(`跳过 ${task.skippedFiles}`);
  }
  if (task.failedFiles > 0) {
    parts.push(`失败 ${task.failedFiles}`);
  }
  return `上传结束：${parts.join("，")}`;
}

/**
 * 处理任务结束后的提示、刷新与延迟移除。
 *
 * @param {UploadTask} task 上传任务。
 */
function handleTaskFinished(task) {
  if (task.completedFiles > 0) {
    callbacks.onRefresh();
  }

  if (task.status === TASK_STATUS.FAILED) {
    showError(
      `上传失败：${extractErrorMessage(task.error)}`
    );
  } else if (task.status === TASK_STATUS.CANCELED) {
    showInfo(`已终止上传：${task.completedFiles} 个文件已完成`);
  } else if (
    task.skippedFiles > 0 ||
    task.failedFiles > 0 ||
    task.completedFiles < task.totalFiles
  ) {
    showInfo(buildFinishedMessage(task));
  } else {
    showSuccess(`上传完成：${task.completedFiles} 个文件`);
  }

  scheduleTaskRemoval(task);
}

/**
 * 定时采样活跃任务速度并刷新面板。
 */
function tick() {
  let hasActive = false;
  for (const task of tasks) {
    if (task.status === TASK_STATUS.UPLOADING) {
      task.speedTracker.sample(task.getUploadedBytes());
      hasActive = true;
    }
  }
  if (hasActive) {
    notifyTasksChanged();
  }
}

/**
 * 启动管理器定时器。
 */
export function initializeUploadManager() {
  if (tickTimer !== null) {
    return;
  }
  tickTimer = window.setInterval(tick, TICK_INTERVAL_MILLISECONDS);
}

/**
 * 创建并启动一个上传任务。
 *
 * @param {Array<{file: File, relativePath: string}>} entries 上传条目。
 * @param {string} targetDirectory 目标目录虚拟路径。
 * @returns {UploadTask} 创建的任务。
 */
export function createUploadTask(entries, targetDirectory) {
  const task = new UploadTask({
    entries,
    targetDirectory,
    kind: classifyTask(entries),
  });
  task.notify = notifyTasksChanged;
  task.onConflict = () => {
    callbacks.onRequestOpenPanel();
    notifyTasksChanged();
  };
  task.onFinished = handleTaskFinished;

  tasks.push(task);
  notifyTasksChanged();
  startUploadTask(task);
  return task;
}

/**
 * 暂停指定任务。
 *
 * @param {string} taskId 任务 ID。
 */
export function pauseUploadTaskById(taskId) {
  const task = findUploadTask(taskId);
  if (task) {
    pauseUploadTask(task);
  }
}

/**
 * 继续指定任务。
 *
 * @param {string} taskId 任务 ID。
 */
export function resumeUploadTaskById(taskId) {
  const task = findUploadTask(taskId);
  if (task) {
    resumeUploadTask(task);
  }
}

/**
 * 请求终止任务：先暂停，再弹出确认框。
 *
 * @param {string} taskId 任务 ID。
 * @returns {Promise<void>} 处理完成后 resolve。
 */
export async function requestTerminateUploadTask(taskId) {
  const task = findUploadTask(taskId);
  if (!task || !isTaskOngoing(task.status)) {
    return;
  }

  const shouldResumeAfterCancel =
    task.status === TASK_STATUS.UPLOADING ||
    task.status === TASK_STATUS.PENDING;
  if (shouldResumeAfterCancel) {
    pauseUploadTask(task);
  }

  const confirmed = await showConfirmDialog({
    title: "终止上传任务",
    message: `确定要终止“${task.getDisplayName()}”的上传任务吗？已上传的部分将被丢弃。`,
    confirmLabel: "终止",
    danger: true,
  });

  if (!confirmed) {
    if (
      shouldResumeAfterCancel &&
      task.status === TASK_STATUS.PAUSED
    ) {
      resumeUploadTask(task);
    }
    return;
  }

  if (isTaskOngoing(task.status)) {
    terminateUploadTask(task);
  }
}

/**
 * 处理任务同名文件冲突。
 *
 * @param {string} taskId 任务 ID。
 * @param {"skip"|"replace"} decision 用户选择。
 */
export function resolveUploadTaskConflict(taskId, decision) {
  const task = findUploadTask(taskId);
  if (task) {
    resolveTaskConflict(task, decision);
  }
}
