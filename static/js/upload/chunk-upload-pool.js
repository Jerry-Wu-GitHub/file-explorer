/**
 * 分片并发上传工作池。
 *
 * 按固定并发度上传会话中缺失的分片。暂停或终止时由任务中止活跃请求，
 * 尚未成功返回的分片会在恢复后重新上传。
 */

import { uploadChunk } from "../api/uploads.js";
import { MAX_CONCURRENT_CHUNK_UPLOADS } from "../config.js";
import { UploadHaltedError } from "./task-errors.js";
import { TASK_STATUS } from "./upload-status.js";

export class ChunkUploadPool {
  /**
   * @param {Object} task 上传任务。
   * @param {{file: File, relativePath: string}} entry 条目。
   * @param {Object} session 分片会话状态。
   */
  constructor(task, entry, session) {
    this.task = task;
    this.entry = entry;
    this.session = session;
    this.pending = [];
    for (let index = 0; index < session.totalChunks; index += 1) {
      if (!session.uploadedChunks.has(index)) {
        this.pending.push(index);
      }
    }
    this.nextIndex = 0;
    this.firstError = null;
  }

  /**
   * 执行所有待上传分片。
   *
   * @returns {Promise<void>} 全部分片完成后 resolve。
   */
  async run() {
    const workerCount = Math.min(
      MAX_CONCURRENT_CHUNK_UPLOADS,
      this.pending.length
    );
    const workers = [];
    for (let index = 0; index < workerCount; index += 1) {
      workers.push(this.runWorker());
    }
    await Promise.all(workers);
    if (this.firstError) {
      throw this.firstError;
    }
  }

  /**
   * 工作池中的单个并发工作者。
   *
   * @returns {Promise<void>} 无待处理分片时 resolve。
   */
  async runWorker() {
    while (true) {
      if (this.task.status !== TASK_STATUS.UPLOADING) {
        this.firstError = this.firstError || new UploadHaltedError();
        return;
      }
      const chunkNumber = this.pending[this.nextIndex];
      this.nextIndex += 1;
      if (chunkNumber === undefined) {
        return;
      }
      try {
        await this.uploadChunkNumber(chunkNumber);
      } catch (error) {
        this.firstError = this.firstError || error;
        return;
      }
    }
  }

  /**
   * 上传指定编号的分片。
   *
   * @param {number} chunkNumber 分片编号。
   * @returns {Promise<void>} 无返回值。
   */
  async uploadChunkNumber(chunkNumber) {
    const start = chunkNumber * this.session.chunkSize;
    const end = Math.min(start + this.session.chunkSize, this.entry.file.size);
    const blob = this.entry.file.slice(start, end);
    const controller = new AbortController();
    this.task.addController(controller);
    try {
      await uploadChunk(this.session.uploadId, chunkNumber, blob, {
        signal: controller.signal,
        onProgress: (loaded, total) => {
          const ratio = total > 0 ? loaded / total : 0;
          const size = Math.min(blob.size, blob.size * ratio);
          this.task.inFlightBytes.set(chunkNumber, Math.round(size));
        },
      });
      this.task.inFlightBytes.delete(chunkNumber);
      this.session.uploadedChunks.add(chunkNumber);
      this.task.currentBaseBytes += blob.size;
    } catch (error) {
      this.task.inFlightBytes.delete(chunkNumber);
      throw error;
    } finally {
      this.task.removeController(controller);
    }
  }
}
