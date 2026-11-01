/**
 * 单文件上传执行。
 *
 * 根据文件大小选择小文件上传或分片上传，处理同名文件冲突、暂停中止
 * 与当前条目完成后的进度推进。
 */

import { uploadSmallFile } from "../api/files.js";
import {
  completeUpload,
  initializeUpload,
} from "../api/uploads.js";
import {
  CHUNKED_UPLOAD_THRESHOLD,
  DEFAULT_CHUNK_SIZE,
  MAX_CHUNKS,
} from "../config.js";
import { ChunkUploadPool } from "./chunk-upload-pool.js";
import {
  getFilename,
  joinVirtualPath,
  resolveEntryDirectory,
} from "./path-helpers.js";
import {
  isAbortError,
  isFileConflict,
  UploadHaltedError,
} from "./task-errors.js";
import { cancelTaskSession } from "./task-session.js";
import { TASK_STATUS } from "./upload-status.js";

/**
 * 根据文件大小选择分片大小。
 *
 * @param {number} fileSize 文件总字节数。
 * @returns {number} 分片大小。
 */
function pickChunkSize(fileSize) {
  if (fileSize <= DEFAULT_CHUNK_SIZE * MAX_CHUNKS) {
    return DEFAULT_CHUNK_SIZE;
  }
  return Math.ceil(fileSize / MAX_CHUNKS);
}

/**
 * 将任务标记为冲突并暂停。
 *
 * @param {Object} task 上传任务。
 * @param {{file: File, relativePath: string}} entry 冲突条目。
 */
function pauseForConflict(task, entry) {
  task.status = TASK_STATUS.CONFLICT;
  task.conflict = {
    filename: getFilename(entry.relativePath),
    relativePath: entry.relativePath,
  };
  task.currentBaseBytes = 0;
  task.inFlightBytes.clear();
  task.speedTracker.pause();
  cancelTaskSession(task);
  task.notify();
  task.onConflict(task);
}

/**
 * 小文件上传，带进度、暂停与覆盖支持。
 *
 * @param {Object} task 上传任务。
 * @param {{file: File, relativePath: string}} entry 条目。
 * @returns {Promise<Object>} 上传后的元数据。
 */
async function uploadSmallEntry(task, entry) {
  const targetDirectory = resolveEntryDirectory(
    task.targetDirectory,
    entry.relativePath
  );
  const filename = getFilename(entry.relativePath);
  const controller = new AbortController();
  const progressKey = `file-${task.currentIndex}`;
  task.addController(controller);
  try {
    const metadata = await uploadSmallFile(targetDirectory, entry.file, {
      filename,
      overwrite: task.overwriteCurrentFile,
      signal: controller.signal,
      onProgress(loaded, total) {
        const ratio = total > 0 ? loaded / total : 0;
        const size = Math.min(entry.file.size, entry.file.size * ratio);
        task.inFlightBytes.set(progressKey, Math.round(size));
      },
    });
    task.inFlightBytes.delete(progressKey);
    task.currentBaseBytes = entry.file.size;
    return metadata;
  } finally {
    task.removeController(controller);
    task.inFlightBytes.delete(progressKey);
  }
}

/**
 * 分片上传单个大文件。
 *
 * @param {Object} task 上传任务。
 * @param {{file: File, relativePath: string}} entry 条目。
 * @returns {Promise<Object>} 上传后的元数据。
 */
async function uploadChunkedEntry(task, entry) {
  const targetPath = joinVirtualPath(
    resolveEntryDirectory(task.targetDirectory, entry.relativePath),
    getFilename(entry.relativePath)
  );

  if (!task.session) {
    const session = await initializeUpload({
      path: targetPath,
      size: entry.file.size,
      chunkSize: pickChunkSize(entry.file.size),
      overwrite: task.overwriteCurrentFile,
    });
    task.session = {
      uploadId: session.uploadId,
      chunkSize: session.chunkSize,
      totalChunks: session.totalChunks,
      uploadedChunks: new Set(session.uploadedChunks || []),
    };
    task.currentBaseBytes = session.uploadedBytes || 0;
  }

  const pool = new ChunkUploadPool(task, entry, task.session);
  await pool.run();
  task.currentBaseBytes = entry.file.size;
  task.inFlightBytes.clear();
  const uploadId = task.session.uploadId;
  const metadata = await completeUpload(uploadId);
  task.session = null;
  return metadata;
}

/**
 * 上传当前索引对应的单个文件。
 *
 * @param {Object} task 上传任务。
 * @returns {Promise<void>} 无返回值。
 */
export async function uploadCurrentEntry(task) {
  const entry = task.getCurrentEntry();
  if (!entry) {
    return;
  }
  task.currentPhase = `正在上传：${entry.relativePath}`;
  task.notify();
  try {
    if (entry.file.size >= CHUNKED_UPLOAD_THRESHOLD) {
      await uploadChunkedEntry(task, entry);
    } else {
      await uploadSmallEntry(task, entry);
    }
  } catch (error) {
    if (isAbortError(error)) {
      task.inFlightBytes.clear();
      throw error;
    }
    if (isFileConflict(error) && !task.overwriteCurrentFile) {
      pauseForConflict(task, entry);
      throw new UploadHaltedError();
    }
    throw error;
  }
}

/**
 * 记录当前文件完成，并推进到下一个条目。
 *
 * @param {Object} task 上传任务。
 */
export function finishCurrentEntry(task) {
  const entry = task.getCurrentEntry();
  if (!entry) {
    return;
  }
  task.completedFiles += 1;
  task.completedBytes += entry.file.size;
  task.currentIndex += 1;
  task.currentBaseBytes = 0;
  task.inFlightBytes.clear();
  task.overwriteCurrentFile = false;
  task.currentPhase = "";
  task.notify();
}
