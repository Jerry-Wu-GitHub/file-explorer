/**
 * 分片上传会话清理。
 */

import { cancelUpload } from "../api/uploads.js";

/**
 * 取消任务当前的分片会话。
 *
 * @param {Object} task 上传任务。
 * @returns {Promise<void>} 无返回值。
 */
export async function cancelTaskSession(task) {
  const session = task.session;
  task.session = null;
  if (!session) {
    return;
  }
  try {
    await cancelUpload(session.uploadId);
  } catch (error) {
    console.warn(`取消上传会话失败：${session.uploadId}`, error);
  }
}
