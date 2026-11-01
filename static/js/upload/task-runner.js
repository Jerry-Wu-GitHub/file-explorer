/**
 * 上传任务调度器。
 *
 * 负责执行单个上传任务：准备目录、按顺序上传文件，以及暂停、继续、
 * 终止与同名文件冲突处理。任务被暂停时中止活跃请求，再次开始时从
 * 已完成部分继续。
 */

import { ensureUploadDirectories } from "./directory-creator.js";
import {
  isAbortError,
  UploadHaltedError,
} from "./task-errors.js";
import { cancelTaskSession } from "./task-session.js";
import {
  finishCurrentEntry,
  uploadCurrentEntry,
} from "./task-uploader.js";
import { TASK_KIND, TASK_STATUS } from "./upload-status.js";

/**
 * 结束任务并通知界面。
 *
 * @param {Object} task 上传任务。
 * @param {string} status 最终状态。
 */
function finishUploadTask(task, status) {
  task.status = status;
  task.finishedAt = Date.now();
  task.speedTracker.pause();
  task.notify();
  task.onFinished(task);
}

/**
 * 将任务标记为失败。
 *
 * @param {Object} task 上传任务。
 * @param {*} error 错误对象。
 */
function failUploadTask(task, error) {
  task.error = error;
  cancelTaskSession(task);
  finishUploadTask(task, TASK_STATUS.FAILED);
}

/**
 * 批量任务中单个文件失败后，跳过该文件继续后续上传。
 *
 * @param {Object} task 上传任务。
 * @param {*} error 错误对象。
 */
function skipFailedEntry(task, error) {
  const entry = task.getCurrentEntry();
  task.failedFiles += 1;
  task.failedBytes += entry ? entry.file.size : 0;
  task.error = error;
  task.currentIndex += 1;
  task.currentBaseBytes = 0;
  task.inFlightBytes.clear();
  task.overwriteCurrentFile = false;
  task.currentPhase = "";
  task.speedTracker.resetProgress(task.getUploadedBytes());
  cancelTaskSession(task);
  task.notify();
}

/**
 * 启动或恢复上传任务。
 *
 * @param {Object} task 上传任务。
 * @returns {Promise<void>} 任务本轮执行结束后 resolve。
 */
export async function startUploadTask(task) {
  if (task.running) {
    task.resumePending = true;
    return;
  }

  task.running = true;
  task.resumePending = false;
  task.status = TASK_STATUS.UPLOADING;
  task.speedTracker.resetProgress(task.getUploadedBytes());
  task.speedTracker.resume();
  task.notify();

  try {
    if (!task.directoriesEnsured) {
      task.currentPhase = "正在准备目录…";
      task.notify();
      await ensureUploadDirectories(task.entries, task.targetDirectory);
      task.directoriesEnsured = true;
      task.currentPhase = "";
    }

    while (task.currentIndex < task.entries.length) {
      if (task.status !== TASK_STATUS.UPLOADING) {
        return;
      }
      try {
        await uploadCurrentEntry(task);
        finishCurrentEntry(task);
      } catch (error) {
        if (error instanceof UploadHaltedError || isAbortError(error)) {
          throw error;
        }
        skipFailedEntry(task, error);
        if (task.kind !== TASK_KIND.BATCH) {
          throw error;
        }
      }
    }

    finishUploadTask(task, TASK_STATUS.COMPLETED);
  } catch (error) {
    if (error instanceof UploadHaltedError || isAbortError(error)) {
      return;
    }
    failUploadTask(task, error);
  } finally {
    task.running = false;
    const shouldResume =
      task.resumePending && task.status === TASK_STATUS.UPLOADING;
    task.resumePending = false;
    if (shouldResume) {
      startUploadTask(task);
    }
  }
}

/**
 * 暂停任务，并中止正在进行的请求。
 *
 * @param {Object} task 上传任务。
 */
export function pauseUploadTask(task) {
  if (
    task.status !== TASK_STATUS.UPLOADING &&
    task.status !== TASK_STATUS.PENDING
  ) {
    return;
  }
  task.status = TASK_STATUS.PAUSED;
  task.speedTracker.pause();
  task.abortActiveRequests();
  task.inFlightBytes.clear();
  task.notify();
}

/**
 * 继续已暂停的任务。
 *
 * @param {Object} task 上传任务。
 */
export function resumeUploadTask(task) {
  if (task.status !== TASK_STATUS.PAUSED) {
    return;
  }
  task.status = TASK_STATUS.UPLOADING;
  task.speedTracker.resume();
  task.notify();
  startUploadTask(task);
}

/**
 * 终止任务，取消分片会话并清理状态。
 *
 * @param {Object} task 上传任务。
 */
export function terminateUploadTask(task) {
  task.status = TASK_STATUS.CANCELED;
  task.conflict = null;
  task.finishedAt = Date.now();
  task.speedTracker.pause();
  task.abortActiveRequests();
  task.inFlightBytes.clear();
  cancelTaskSession(task);
  task.notify();
  task.onFinished(task);
}

/**
 * 处理同名文件冲突的用户选择。
 *
 * @param {Object} task 上传任务。
 * @param {"skip"|"replace"} decision 用户选择。
 */
export function resolveTaskConflict(task, decision) {
  if (task.status !== TASK_STATUS.CONFLICT || !task.conflict) {
    return;
  }
  task.conflict = null;
  if (decision === "skip") {
    const entry = task.getCurrentEntry();
    task.skippedFiles += 1;
    task.skippedBytes += entry ? entry.file.size : 0;
    task.currentIndex += 1;
    task.currentBaseBytes = 0;
    task.inFlightBytes.clear();
    task.session = null;
    task.overwriteCurrentFile = false;
  } else {
    task.overwriteCurrentFile = true;
  }
  task.status = TASK_STATUS.UPLOADING;
  task.speedTracker.resetProgress(task.getUploadedBytes());
  task.speedTracker.resume();
  task.notify();
  startUploadTask(task);
}
