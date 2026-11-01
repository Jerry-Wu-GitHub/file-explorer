/**
 * 上传任务统计指标与统计网格。
 */

import {
  formatDuration,
  formatPercent,
  formatRemainingTime,
  formatSize,
  formatSpeed,
} from "../format.js";
import { TASK_KIND, TASK_STATUS } from "./upload-status.js";

/**
 * 计算任务的展示指标。
 *
 * @param {Object} task 上传任务。
 * @param {number} now 当前毫秒时间戳。
 * @returns {Object} 指标集合。
 */
export function calculateMetrics(task, now) {
  const uploadedBytes = task.getUploadedBytes();
  const remainingBytes = task.getRemainingBytes();
  const percent =
    task.totalBytes > 0
      ? (uploadedBytes / task.totalBytes) * 100
      : task.status === TASK_STATUS.COMPLETED
      ? 100
      : 0;
  const elapsedSeconds = task.speedTracker.getElapsedSeconds(now);
  const averageSpeed =
    elapsedSeconds > 0 ? uploadedBytes / elapsedSeconds : 0;
  const instantaneousSpeed =
    task.status === TASK_STATUS.UPLOADING
      ? task.speedTracker.getInstantaneousSpeed()
      : 0;
  const remainingSeconds =
    remainingBytes <= 0
      ? 0
      : averageSpeed > 0
      ? remainingBytes / averageSpeed
      : Number.POSITIVE_INFINITY;

  return {
    uploadedBytes,
    remainingBytes,
    percent,
    elapsedSeconds,
    averageSpeed,
    instantaneousSpeed,
    remainingSeconds,
  };
}

/**
 * 创建单个统计项。
 *
 * @param {string} label 名称。
 * @param {string} value 值。
 * @returns {HTMLElement} 统计项元素。
 */
function createStatItem(label, value) {
  const item = document.createElement("div");
  item.className = "upload-task__stat";
  const name = document.createElement("span");
  name.className = "upload-task__stat-label";
  name.textContent = label;
  const content = document.createElement("strong");
  content.className = "upload-task__stat-value";
  content.textContent = value;
  item.append(name, content);
  return item;
}

/**
 * 创建统计网格。
 *
 * @param {Object} task 上传任务。
 * @param {Object} metrics 指标集合。
 * @returns {HTMLElement} 统计网格元素。
 */
export function createStatsGrid(task, metrics) {
  const grid = document.createElement("div");
  grid.className = "upload-task__stats";
  const isBatch = task.kind === TASK_KIND.BATCH;

  const stats = [["总大小", formatSize(task.totalBytes)]];
  if (isBatch) {
    stats.push(["总文件数", `${task.totalFiles}`]);
  }
  stats.push(["已上传大小", formatSize(metrics.uploadedBytes)]);
  if (isBatch) {
    stats.push(["已上传文件数", `${task.completedFiles}`]);
  }
  stats.push(["剩余大小", formatSize(metrics.remainingBytes)]);
  if (isBatch) {
    const remainingFiles =
      task.totalFiles -
      task.completedFiles -
      task.skippedFiles -
      task.failedFiles;
    stats.push(["剩余文件数", `${Math.max(0, remainingFiles)}`]);
  }
  stats.push(
    ["已上传百分比", formatPercent(metrics.percent)],
    ["已用时间", formatDuration(metrics.elapsedSeconds)],
    ["平均速度", formatSpeed(metrics.averageSpeed)],
    ["瞬时速度", formatSpeed(metrics.instantaneousSpeed)],
    ["预计剩余", formatRemainingTime(metrics.remainingSeconds)]
  );

  for (const [label, value] of stats) {
    grid.appendChild(createStatItem(label, value));
  }
  return grid;
}
