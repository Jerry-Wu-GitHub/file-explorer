/**
 * 上传任务状态与类型常量。
 *
 * 供任务模型、调度器与面板共享，避免在各模块中散落字符串字面量。
 */

/** 上传任务状态。 */
export const TASK_STATUS = Object.freeze({
  PENDING: "pending",
  UPLOADING: "uploading",
  PAUSED: "paused",
  CONFLICT: "conflict",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELED: "canceled",
});

/** 上传任务类型。 */
export const TASK_KIND = Object.freeze({
  SINGLE: "single",
  SINGLE_CHUNKED: "single-chunked",
  BATCH: "batch",
});

/** 仍在进行中的任务状态集合。 */
const ONGOING_STATUSES = new Set([
  TASK_STATUS.PENDING,
  TASK_STATUS.UPLOADING,
  TASK_STATUS.PAUSED,
  TASK_STATUS.CONFLICT,
]);

/**
 * 判断任务是否仍在进行中。
 *
 * @param {string} status 任务状态。
 * @returns {boolean} 是否为进行中状态。
 */
export function isTaskOngoing(status) {
  return ONGOING_STATUSES.has(status);
}

/**
 * 返回任务类型对应的中文名称。
 *
 * @param {string} kind 任务类型。
 * @returns {string} 中文名称。
 */
export function getTaskKindLabel(kind) {
  if (kind === TASK_KIND.SINGLE_CHUNKED) {
    return "分片上传";
  }
  if (kind === TASK_KIND.BATCH) {
    return "批量上传";
  }
  return "单文件上传";
}
